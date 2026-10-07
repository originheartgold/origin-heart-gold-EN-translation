/* Origin HG JP v4.0.3. Addresses are checked by text_speed_patch.py.
 * Original implementation: no upstream game source is included here. */
typedef unsigned char u8;
typedef unsigned short u16;
typedef unsigned int u32;
#include "labels.h"
#define FN(addr, type) ((type)(addr))
#define U32(p,o) (*(u32 *)((u8 *)(p)+(o)))
#define U16(p,o) (*(u16 *)((u8 *)(p)+(o)))
#define U8(p,o) (*(u8 *)((u8 *)(p)+(o)))
/* Text speed (D-1604): the two bits 2..3 of the Options record hold 1 for FAST;
 * every other value (0: NORMAL and existing saves; 2 and 3: unreleased or unknown
 * values) is NORMAL, the hack's original printer task. Returns 1 for FAST. */
static inline unsigned fast(void) {
    void *save=FN(0x02001195,void *(*)(void))();
    /* This accessor uses the main runtime pointer, published at 0x02000cda
     * only after SaveData construction, block metadata and Options init/load
     * have completed. Before publication it is null. The earlier internal
     * constructor pointer is a different global and must not be used here.
     * SaveData + 4 means a cartridge save exists, not runtime readiness:
     * fresh games have initialized Options while that flag is still zero. */
    if (!save) return 0;
    u16 *opts=FN(0x02029349,u16 *(*)(void *))(save);
    if (!opts) return 0;
    return ((*opts>>2)&3)==1;
}
/* Frame timing (work/notes/text_speed_vcount.md). The game loop wakes at the
 * start of VBlank (display line 192), runs the field or battle work, then waits
 * for the next VBlank. If it is still running when that VBlank starts, the wait
 * misses it and the frame is dropped. Before each extra glyph the batching loop
 * predicts where the loop will end from costs measured at run time:
 *   now + (cost of one more glyph) + (rest of the loop after the batch)
 * and draws the glyph only if that ends before line 192.
 * VCOUNT is the display line I/O register (0..191 drawn, 192..262 VBlank).
 * VBLANKS is the SDK's VBlank counter (HW_VBLANK_COUNT_BUF, the word that
 * OS_GetVBlankCount reads). Neither is ARM9 code, so neither has a reviewed
 * dependency range. */
#define VCOUNT (*(volatile u16 *)0x04000006)
#define VBLANKS (*(volatile u8 *)0x027ffc3c)
#define LINES 263
#define VBLANK_LINE 192
/* Eight recent samples of each cost; a slot of 0 is empty.
 * Glyph: the lines one extra glyph took, from the reading after the previous
 * glyph to the reading after it (render and the loop's own checks), the exact
 * quantity the decision predicts. A task's first glyph is not a sample: it runs
 * after the field work with cold caches and costs about two lines more. With
 * no extra glyph measured since power-on the glyph counts as GLYPH_SEED, the
 * largest glyph cost measured in any scene (first glyphs included; extra glyphs
 * cost at most 11).
 * Rest: lines from the end of a batch that drew to the end of the game loop
 * pass (window copy, task exit, the rest of the loop). With none measured it
 * counts as REST_SEED, about twice the largest rest measured in any scene (11),
 * so a printer's first frame in a new scene draws a second glyph only well
 * before VBlank. After STALE loop passes in which no batching task ran (no text
 * on screen, e.g. a map change) the rest history is cleared, because the new
 * scene's loop may be heavier. A printer waiting for a button still runs its
 * task and keeps the history.
 * MARGIN: VCOUNT counts whole lines; the current line can be up to one line
 * later than read. The maxima of eight samples already cover the rounding of
 * the two costs.
 * SHORT_REST: while the rest history holds fewer than SHORT samples, the rest
 * counts at least SHORT_REST lines, the typical rest (7 lines in 371 of 432
 * samples over 17 field scenes; 6 in 47, 8 in 14). Measured (FAST, 2026-10-07):
 * a next rest exceeded the largest earlier one by 2 lines only with a single low
 * sample (Route 1 promoter: 6, then 8: a dropped frame); against the floor every
 * excess was at most 1 line, as with a full history, which MARGIN covers
 * (work/notes/text_speed_vcount.md). A floor, not an extra margin: a short
 * history of typical rests decides exactly as before. */
#define SLOTS 8
#define GLYPH_SEED 13
#define REST_SEED 20
#define STALE 60
#define MARGIN 1
#define SHORT 3
#define SHORT_REST 7
/* RAM use: these 26 bytes, zero at boot, in the payload's ITCM block (the
 * SDK's ITCM arena starts after them). One global state: glyph costs do not
 * depend on the printer, and the rest belongs to the frame, not the printer. */
struct frame_state {
    u8 glyph[SLOTS];      /* recent glyph costs in lines (0: not measured; at most 255) */
    u8 rest[SLOTS];       /* recent rests in lines: batch end to loop end (0: empty; 1..255) */
    u8 next_glyph, next_rest;
    u8 marked;            /* a batch ended in this loop pass; its rest is still open */
    u8 idle;              /* loop passes without a batching task (stops at STALE) */
    u16 mark_line;        /* VCOUNT at that batch end */
    u8 mark_vblanks;      /* VBLANKS at that batch end */
    u8 ran;               /* a batching task ran in this loop pass */
    u8 end_vblanks;       /* VBLANKS at the previous loop pass end (pass_end) */
    u8 ended;             /* end_vblanks is valid (a pass has ended since power-on) */
};
extern struct frame_state text_speed_state;
static unsigned lines_between(unsigned from,unsigned to) {
    return to>=from?to-from:to+LINES-from;
}
/* End of a batch that drew: remember when, so frame_end can measure the rest.
 * Only batches that drew count: the rest of such a batch includes the window
 * copy to VRAM (about six lines), which a task that only waits for input skips. */
static void mark(struct frame_state *s) {
    s->mark_vblanks=VBLANKS;
    s->mark_line=VCOUNT;
    s->marked=1;
}
/* Called by the game loop as its last step before the wait for VBlank, in place
 * of its call to 0x020272d4 (which it still makes first). Measures the rest of
 * the latest batch in this loop pass: lines from its end to here. The VBlank
 * counter must agree with the lines: exactly one VBlank in between if the
 * interval crossed line 192, else none. Otherwise (the loop waited for VBlank
 * elsewhere in between) the sample is discarded. */
void frame_end(void) {
    FN(0x020272d5,void (*)(void))();
    struct frame_state *s=&text_speed_state;
    unsigned vblanks=VBLANKS,line=VCOUNT;
    if(s->marked) {
        unsigned from=s->mark_line,rest=lines_between(from,line);
        unsigned crossed=from<VBLANK_LINE?from+rest>=VBLANK_LINE:from+rest>=VBLANK_LINE+LINES;
        s->marked=0;
        if(((vblanks-s->mark_vblanks)&255)==crossed) {
            s->rest[s->next_rest]=rest>255?255:rest?rest:1;
            s->next_rest=(s->next_rest+1)&(SLOTS-1);
        }
    }
    if(s->ran) s->idle=0;
    else if(s->idle<STALE && ++s->idle==STALE)
        for(unsigned i=0;i<SLOTS;i++) s->rest[i]=0;
    s->ran=0;
}
/* May the batch draw one more glyph at display line now? */
static unsigned room(struct frame_state *s,unsigned now) {
    /* Lines left until the next VBlank starts (1..263). In VBlank (battle
     * text, or a frame already lost) the next VBlank is a whole frame away. */
    unsigned left=now<VBLANK_LINE?VBLANK_LINE-now:VBLANK_LINE+LINES-now;
    unsigned glyph=0,rest=0,low=255,samples=0;
    for(unsigned i=0;i<SLOTS;i++) {
        unsigned g=s->glyph[i],r=s->rest[i];
        if(g>glyph) glyph=g;
        if(r>rest) rest=r;
        if(r && r<low) low=r;
        if(r) samples++;
    }
    if(!glyph) glyph=GLYPH_SEED;
    if(!rest) {rest=REST_SEED; low=0;}
    else if(samples<SHORT && rest<SHORT_REST) rest=SHORT_REST;
    /* Fits: one more glyph and the rest end before VBlank. */
    if(left>=glyph+rest+MARGIN) return 1;
    /* Lost: even the shortest recent rest ends after VBlank if the batch
     * stops now, so the frame is dropped anyway; its time runs on to the
     * following VBlank, and the batch may use it (still within its budget). */
    return left<low;
}
/* NORMAL, unpublished options, callbacks and explicit delays use the original
 * printer task (one step per task). FAST draws batches of up to three glyphs. */
#define FAST_BUDGET 3
void print_task(void *task, void *p) {
    if (!fast() || U32(p,0x1c) || (U8(p,0x29)&127)) {
        FN(0x02020a1d,void (*)(void *,void *))(task,p); return;
    }
    if (*(volatile u8 *)0x021d0ef4) return;
    struct frame_state *s=&text_speed_state;
    s->ran=1;
    unsigned budget=FAST_BUDGET;
    unsigned dirty=0;
    FN(0x02020a9d,void (*)(unsigned,unsigned,unsigned))(U8(p,0x15),U8(p,0x16),U8(p,0x17));
    unsigned before=0,extra=0;
    for(;;) {
        U16(p,0x2e)=0;
        unsigned result=FN(0x02020a89,unsigned (*)(void *))(p);
        unsigned now=VCOUNT;
        if (result==0) {
            dirty=1;
            if(extra) {
                unsigned cost=lines_between(before,now);
                s->glyph[s->next_glyph]=cost>255?255:cost;
                s->next_glyph=(s->next_glyph+1)&(SLOTS-1);
            }
        }
        if (result==1) {
            if(dirty) {
                mark(s);
                FN(0x0201dda9,void (*)(void *))((void *)U32(p,4));
            }
            FN(0x0202075d,void (*)(unsigned))(U8(p,0x2c)); return;
        }
        /* After a glyph (result 0) RenderText is in state 0 with its delay
           counter +0x2a = +0x29&127 = 0, so this state test never fires today;
           it is kept as a guard (see text_speed_release_checks.md). */
        if(result!=0 || U8(p,0x28) || U8(p,0x2a)) break;
        /* Stop before every non-glyph control, including extended controls.
           A newline (0xe000) is rendered in the same step as the unit after it
           (the native RenderFont repeat dispatcher), so look past newlines: a
           newline before the end of the text or a prompt is that control's step,
           which the original printer takes in the next task. */
        const u16 *q=*(const u16 **)((u8 *)p);
        u16 next=*q;
        while(next==0xe000) next=*++q;
        if(next==0xffff || next==0xfffe || next==0x25bc || next==0x25bd || next==0xf0fd) break;
        if(!--budget) break;
        if(!room(s,now)) break;
        before=now;
        extra=1;
    }
    if(dirty) {
        mark(s);
        FN(0x0201dda9,void (*)(void *))((void *)U32(p,4));
    }
}
/* Music still uses the low two bits. Text speed lives in the upper two bits
 * of the historical four-bit music field. Other settings are untouched.
 * The row shows NORMAL (choice 0) or FAST (choice 1): stored 1 shows FAST,
 * every other stored value shows NORMAL (D-1604). */
void load_rows(void *d) {
    FN(0x021e5335,void (*)(void *))(d);
    U16(d,0x27e)=((U16((void *)U32(d,0x24),0)>>2)&3)==1;
    U16(d,0x2d2)=0;
}
void *load_choice(void *msg,unsigned id) {
    if(id>=41 && id<=42) {
        void *s=FN(0x02026865,void *(*)(unsigned,unsigned))(16,38);
        FN(0x02026eb9,void (*)(void *,const u16 *,unsigned))(s,labels[id-40],11);
        return s;
    }
    return FN(0x0200bb41,void *(*)(void *,unsigned))(msg,id);
}
void load_label(void *msg,unsigned id,void *str) {
    if(id==7) FN(0x02026eb9,void (*)(void *,const u16 *,unsigned))(str,labels[0],11);
    else FN(0x0200bb0d,void (*)(void *,unsigned,void *))(msg,id,str);
}
void commit_speed(void *d) {
    if((U32(d,0x10)&3)==1) {
        u16 *opts=(u16 *)U32(d,0x24);
        unsigned m=U16(d,0x27e)==1;
        *opts=(*opts&~12)|(m<<2);
    }
}
/* Called at the exit's existing free-data call. Read our value before free. */
void exit_free(void *manager) {
    void *d=FN(0x020071ad,void *(*)(void *))(manager);
    commit_speed(d);
    FN(0x020071b1,void (*)(void *))(manager);
}
/* Existing font/palette and arrow assets, with a compact seven-row layout. */
void draw_label(void *win,unsigned font,void *str,unsigned x,unsigned y,unsigned speed,unsigned color,void *cb) {
    FN(0x02020835,void (*)(void *,unsigned,void *,unsigned,unsigned,unsigned,unsigned,void *))(win,font,str,x,y,speed,0x00010200,cb);
}
void setup_sprites(void *d) {
    FN(0x021e5acd,void (*)(void *))(d);
    for(unsigned i=5;i<7;i++) FN(0x0200d8cd,void (*)(void *,unsigned))((void *)U32(d,0x32c+4*i),0);
    for(unsigned i=0;i<5;i++) FN(0x02024e49,void (*)(void *,unsigned))((void *)U32(d,0x32c+4*i),0);
}
/* Printer catch-up (D-1603). The vanilla game loop runs the print task queue twice
 * per pass (logic is capped at 30 fps, text runs once per VBlank). The hack's loop
 * runs it once per pass and does not cap logic, so when a pass spans two VBlanks
 * (most outdoor maps) text prints at half the vanilla rate. pass_end runs where the
 * vanilla loop makes its second queue run: after the 3D swap request, before the
 * VBlank wait. If a VBlank passed during this pass (the frame is lost, the wait
 * returns only at the following VBlank), each text printer task runs once more, as
 * vanilla does. Passes within one frame (60 fps scenes) are unchanged, and at most
 * one extra run is made per pass (vanilla's two runs per pass). Only the text
 * printer tasks run (the 8 SysTask slots of the printer system at 0x021d0efc, filled
 * by 0x02020728), only when their next step draws a glyph; other queue tasks keep
 * the hack's rate. A task is run as the
 * queue run (0x02020040) runs it: func +0x14 with (task, data +0x10), skipped while
 * its added-during-a-run flag +0x18 is set; only tasks present before the catch-up
 * started run, so a printer added by a callback during the catch-up waits for the
 * next pass. The catch-up only starts when one glyph and the measured rest fit
 * before the next VBlank (the frame model's 'fits'), so it never drops a frame. */
#define PRINTER_TASKS ((u32 *volatile *)0x021d0efc)
void pass_end(void) {
    frame_end();
    struct frame_state *s=&text_speed_state;
    unsigned vblanks=VBLANKS,line=VCOUNT;
    unsigned late=s->ended && ((vblanks-s->end_vblanks)&255)>=2;
    s->end_vblanks=vblanks;
    s->ended=1;
    if(late) {
        unsigned left=line<VBLANK_LINE?VBLANK_LINE-line:VBLANK_LINE+LINES-line;
        unsigned glyph=0,rest=0;
        for(unsigned i=0;i<SLOTS;i++) {
            if(s->glyph[i]>glyph) glyph=s->glyph[i];
            if(s->rest[i]>rest) rest=s->rest[i];
        }
        if(!glyph) glyph=GLYPH_SEED;
        if(!rest) rest=REST_SEED;
        if(left>=glyph+rest+MARGIN) {
            u32 *tasks[8];
            for(unsigned i=0;i<8;i++) tasks[i]=PRINTER_TASKS[i];
            for(unsigned i=0;i<8;i++) {
                u32 *t=tasks[i];
                if(!t || PRINTER_TASKS[i]!=t || t[6] || !t[5]) continue;
                /* Only a printer about to draw a glyph: RenderText in state 0 and the
                 * next unit (past newlines) not a control. Prompts, scrolls, page
                 * clears, waits for a button and the end of the text keep the hack's
                 * one step per pass, so input is polled exactly as before. */
                u8 *p=(u8 *)t[4];
                if(U8(p,0x28)) continue;
                const u16 *q=*(const u16 **)p;
                u16 next=*q;
                while(next==0xe000) next=*++q;
                if(next==0xffff || next==0xfffe || next==0x25bc || next==0x25bd || next==0xf0fd) continue;
                ((void (*)(void *,void *))t[5])(t,p);
            }
        }
    }
    /* A catch-up batch's rest is not a sample: frame_end of the next pass would
     * measure it across the VBlank wait. */
    s->marked=0;
}
/* Pokégear phone calls (D-1600, bug D-1599). Battles leave the renderer's
 * auto-scroll mode on (SetAutoScrollParam(3), never cleared at battle exit),
 * so call pages advanced by themselves after a battle. The single call-page
 * printer in overlay 92 now comes here: clear auto-scroll (both bits, as a
 * field message box does with SetAutoScrollParam(0)), then print exactly as
 * before. The A/B speed-up and touch-advance flags stay as the Pokégear set
 * them. Independent of the text-speed value, including the reserved values. */
unsigned call_print(void *win,unsigned font,void *str,unsigned x,unsigned y,unsigned speed,unsigned color,void *cb) {
    FN(0x02002b51,void (*)(unsigned))(0);
    return FN(0x02020835,unsigned (*)(void *,unsigned,void *,unsigned,unsigned,unsigned,unsigned,void *))(win,font,str,x,y,speed,color,cb);
}
/* Defined last so that it is the last part of the payload block (zero at boot;
 * the gates compare the payload's code and data up to it). */
struct frame_state text_speed_state;
