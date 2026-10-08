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
/* Frame timing (work/notes/text_speed_vcount.md; D-2269, D-2271). The game loop
 * wakes at the start of VBlank (display line 192), runs the field or battle work,
 * then waits for the next VBlank. If it is still running when that VBlank starts,
 * the wait misses it and the frame is dropped. Before each extra glyph the
 * batching loop predicts where the loop will end from costs measured at run time:
 *   now + (cost of one more glyph) + (rest of the loop after the batch) + MARGIN
 * and draws the glyph only if that ends before the next VBlank starts.
 * Time is measured in ticks of the SDK's tick timer (timer 0 at the bus clock /
 * 64 since OS_InitTick; the SDK counts its overflows in OSi_TickCounter): a
 * display line is 2130 bus cycles, RHO = 33.28125 ticks. VCOUNT tells the line,
 * not how far into it the loop is. At FAST the end of a loop pass with time to
 * spare waits for VCOUNT to change (at most one line, time it would spend
 * waiting for VBlank anyway) and keeps that tick as an anchor, the start of a
 * line. Lines keep their length and phase from frame to frame (in DeSmuME a
 * frame sometimes lasts two lines longer, never a part of a line), so for up to
 * MAX_AGE ticks after the anchor the position in the line is the ticks since the
 * anchor modulo RHO. Without a usable anchor (the first text after power-on, a
 * reset of the tick timer: the game calls OS_SetTick in some screens) the
 * payload assumes the worst: the current line is about to end.
 * VCOUNT is the display line I/O register (0..191 drawn, 192..262 VBlank),
 * TM0 the timer 0 counter, IRQF the interrupt request flags (a pending timer 0
 * overflow), VBLANKS the SDK's VBlank counter (HW_VBLANK_COUNT_BUF, the word
 * OS_GetVBlankCount reads), TICKS the low word of OSi_TickCounter (SDK data the
 * reviewed tick interrupt 0x020d2208 maintains). */
#define VCOUNT (*(volatile u16 *)0x04000006)
#define TM0 (*(volatile u16 *)0x04000100)
#define IRQF (*(volatile u32 *)0x04000214)
#define TICKS (*(volatile u32 *)0x021e0a5c)
#define VBLANKS (*(volatile u8 *)0x027ffc3c)
#define LINES 263
#define VBLANK_LINE 192
#define RHO 8520          /* ticks per display line x 256 (2130 / 64) */
#define MAX_AGE 52800     /* about six frames of ticks */
/* Eight recent samples of each cost in ticks; a slot of 0 is empty.
 * Glyph: the ticks one extra glyph took, from the reading after the previous
 * glyph to the reading after it (render and the loop's own checks), the exact
 * quantity the decision predicts. A task's first glyph is not a sample: it runs
 * after the field work with cold caches and costs about two lines more. With
 * no extra glyph measured since power-on the glyph counts as GLYPH_SEED lines,
 * the largest glyph cost measured in any scene (first glyphs included).
 * Rest: ticks from the end of a batch that drew to the end of the game loop
 * pass (window copy, task exit, the rest of the loop). With none measured it
 * counts as REST_SEED lines, about twice the largest rest measured in any scene,
 * so a printer's first frame in a new scene draws a second glyph only well
 * before VBlank. After STALE loop passes in which no batching task ran (no text
 * on screen, e.g. a map change) the rest history is cleared, because the new
 * scene's loop may be heavier. A printer waiting for a button still runs its
 * task and keeps the history.
 * A sample is kept only if its ticks agree with the display lines it spans.
 * The prediction uses the typical recent cost (costs()). A cost spikes now and
 * then: measured in 17 scenes at both input phases (D-2271), a glyph took up to
 * 33 ticks more than the typical glyph, a rest up to 26 more than the typical
 * rest, and both can fall into one decision (glyph +32 and rest +25 dropped a
 * frame with a margin of 50). MARGIN covers both spikes and what the loop does
 * after its last reading (3 ticks) and the rounding of two tick readings (2):
 * 33 + 26 + 3 + 2 = 64 (work/notes/text_speed_vcount.md).
 * SHORT_REST: while the rest history holds fewer than SHORT samples, the rest
 * counts at least SHORT_REST lines, the typical rest. */
#define SLOTS 8
#define GLYPH_SEED 13
#define REST_SEED 20
#define STALE 60
#define MARGIN 64
#define SHORT 3
#define SHORT_REST 7
/* RAM use: these 52 bytes, zero at boot, in the payload's ITCM block (the
 * SDK's ITCM arena starts after them). One global state: glyph costs do not
 * depend on the printer, and the rest belongs to the frame, not the printer. */
struct frame_state {
    u16 glyph[SLOTS];     /* recent glyph costs in ticks (0: not measured) */
    u16 rest[SLOTS];      /* recent rests in ticks: batch end to loop end (0: empty) */
    u32 mark_tick;        /* tick at the end of the latest batch that drew */
    u32 anchor;           /* tick right after VCOUNT changed (a line start) */
    u16 mark_line;        /* VCOUNT at that batch end */
    u8 next_glyph, next_rest;
    u8 marked;            /* a batch ended in this loop pass; its rest is still open */
    u8 idle;              /* loop passes without a batching task (stops at STALE) */
    u8 mark_vblanks;      /* VBLANKS at that batch end */
    u8 ran;               /* a batching task ran in this loop pass */
    u8 end_vblanks;       /* VBLANKS at the previous loop pass end (pass_end) */
    u8 ended;             /* end_vblanks is valid (a pass has ended since power-on) */
    u8 anchored;          /* anchor is set */
    u8 pad;
};
extern struct frame_state text_speed_state;
static unsigned lines_between(unsigned from,unsigned to) {
    return to>=from?to-from:to+LINES-from;
}
static unsigned lines_to_vblank(unsigned line) {
    return line<VBLANK_LINE?VBLANK_LINE-line:VBLANK_LINE+LINES-line;
}
/* The tick count: OSi_TickCounter's low word and TM0, read as OS_GetTick does
 * (a timer overflow not yet counted by its interrupt adds one). */
static inline __attribute__((always_inline)) unsigned ticks(void) {
    unsigned hi,lo;
    do {hi=TICKS; lo=TM0;} while(hi!=TICKS);
    if((IRQF&8) && !(lo&0x8000)) hi++;
    return hi<<16|lo;
}
/* Do dt ticks agree with lines display lines between two readings? The true
 * time is more than lines-1 and less than lines+1 lines (one tick of slack). */
static unsigned agree(unsigned dt,unsigned lines) {
    if(dt>0xffff) return 0;
    dt=(dt+1)<<8;
    return dt+RHO>lines*RHO && dt<(lines+1)*RHO+512;
}
/* x mod RHO for x < 2^25 (Thumb has no divide instruction). */
static unsigned mod_rho(unsigned x) {
    for(unsigned d=RHO<<11;d>=RHO;d>>=1) if(x>=d) x-=d;
    return x;
}
/* Ticks left until the next VBlank starts (line, tick: a reading). From the
 * anchor when it is at most MAX_AGE old, else the least possible. In VBlank
 * (battle text, or a frame already lost) the next VBlank is a whole frame away. */
static unsigned left_ticks(struct frame_state *s,unsigned line,unsigned tick) {
    unsigned n=lines_to_vblank(line)*RHO,age=tick-s->anchor;
    if(s->anchored && age<MAX_AGE) {
        unsigned into=mod_rho(age<<8);
        return n>into?(n-into)>>8:0;
    }
    return (n-RHO)>>8;
}
/* End of a batch that drew: remember when, so frame_end can measure the rest.
 * Only batches that drew count: the rest of such a batch includes the window
 * copy to VRAM (about six lines), which a task that only waits for input skips. */
static inline __attribute__((always_inline)) void mark(struct frame_state *s) {
    s->mark_vblanks=VBLANKS;
    s->mark_line=VCOUNT;
    s->mark_tick=ticks();
    s->marked=1;
}
/* Called by the game loop as its last step before the wait for VBlank, in place
 * of its call to 0x020272d4 (which it still makes first). Measures the rest of
 * the latest batch in this loop pass: ticks from its end to here. The VBlank
 * counter must agree with the lines (exactly one VBlank in between if the
 * interval crossed line 192, else none; otherwise the loop waited for VBlank
 * elsewhere in between) and the ticks with the lines, or the sample is
 * discarded. */
void frame_end(void) {
    FN(0x020272d5,void (*)(void))();
    struct frame_state *s=&text_speed_state;
    unsigned vblanks=VBLANKS,line=VCOUNT,tick=ticks();
    if(s->marked) {
        unsigned from=s->mark_line,lines=lines_between(from,line);
        unsigned crossed=from<VBLANK_LINE?from+lines>=VBLANK_LINE:from+lines>=VBLANK_LINE+LINES;
        unsigned rest=tick-s->mark_tick;
        s->marked=0;
        if(((vblanks-s->mark_vblanks)&255)==crossed && agree(rest,lines)) {
            s->rest[s->next_rest]=rest?rest:1;
            s->next_rest=(s->next_rest+1)&(SLOTS-1);
        }
    }
    if(s->ran) s->idle=0;
    else if(s->idle<STALE && ++s->idle==STALE)
        for(unsigned i=0;i<SLOTS;i++) s->rest[i]=0;
    s->ran=0;
}
/* The lower median of the slots at or above floor (0 when fewer than SHORT). */
static unsigned median(const u16 *v,unsigned floor,unsigned *count) {
    unsigned n=0;
    for(unsigned i=0;i<SLOTS;i++) n+=v[i] && v[i]>=floor;
    *count=n;
    if(n<SHORT) return 0;
    for(unsigned i=0;i<SLOTS;i++) {
        unsigned x=v[i],below=0,same=0;
        if(!x || x<floor) continue;
        for(unsigned j=0;j<SLOTS;j++) {
            if(!v[j] || v[j]<floor) continue;
            below+=v[j]<x;
            same+=v[j]==x;
        }
        if(below<=(n-1)/2 && (n-1)/2<below+same) return x;
    }
    return 0;
}
/* The typical recent glyph cost and rest in ticks, and the shortest recent rest
 * (0: none). A glyph cost is typical among the glyphs that read their font data
 * (at least half the seed, GLYPH_SEED / 2 lines; a glyph whose data was just read
 * costs about half as much). With fewer than SHORT such samples the glyph counts
 * as the largest recent cost, at least the seed; with fewer than SHORT rests the
 * rest counts as the largest recent rest (then at least SHORT_REST lines, below),
 * with none as the seed. */
static unsigned costs(struct frame_state *s,unsigned *rest,unsigned *low,unsigned *samples) {
    unsigned n,seed=(GLYPH_SEED*RHO)>>8,glyph=median(s->glyph,seed/2,&n),r=median(s->rest,1,samples);
    unsigned top=0,l=0xffff,big=0;
    for(unsigned i=0;i<SLOTS;i++) {
        if(s->glyph[i]>top) top=s->glyph[i];
        if(s->rest[i]>big) big=s->rest[i];
        if(s->rest[i] && s->rest[i]<l) l=s->rest[i];
    }
    if(!glyph) glyph=top>seed?top:seed;
    if(!r) r=big;
    if(!r) {r=(REST_SEED*RHO)>>8; l=0;}
    *rest=r; *low=l;
    return glyph;
}
/* May the batch draw one more glyph at this reading? */
static inline __attribute__((always_inline)) unsigned room(struct frame_state *s,unsigned line,unsigned tick) {
    unsigned rest,low,samples;
    unsigned glyph=costs(s,&rest,&low,&samples);
    if(low && samples<SHORT) {
        unsigned floor=(SHORT_REST*RHO)>>8;
        if(rest<floor) rest=floor;
    }
    unsigned left=left_ticks(s,line,tick);
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
    unsigned before=0,before_tick=0,extra=0;
    for(;;) {
        U16(p,0x2e)=0;
        unsigned result=FN(0x02020a89,unsigned (*)(void *))(p);
        unsigned now=VCOUNT,tick=ticks();
        if (result==0) {
            dirty=1;
            if(extra) {
                unsigned cost=tick-before_tick;
                if(agree(cost,lines_between(before,now))) {
                    s->glyph[s->next_glyph]=cost?cost:1;
                    s->next_glyph=(s->next_glyph+1)&(SLOTS-1);
                }
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
        if(!room(s,now,tick)) break;
        before=now;
        before_tick=tick;
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
    unsigned vblanks=VBLANKS,line=VCOUNT,tick=ticks();
    unsigned late=s->ended && ((vblanks-s->end_vblanks)&255)>=2;
    s->end_vblanks=vblanks;
    s->ended=1;
    if(late) {
        unsigned rest,low,samples;
        unsigned glyph=costs(s,&rest,&low,&samples);
        if(left_ticks(s,line,tick)>=glyph+rest+MARGIN) {
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
    /* Anchor (D-2269): at FAST, with at least three lines left before VBlank,
     * wait for VCOUNT to change (at most one line, time the loop would spend
     * waiting for VBlank anyway) and keep that tick, the start of a line.
     * NORMAL, the original printer and the other values never wait here. */
    if(fast()) {
        unsigned from=VCOUNT;
        if(lines_to_vblank(from)>=3) {
            while(VCOUNT==from);
            s->anchor=ticks();
            s->anchored=1;
        }
    }
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
