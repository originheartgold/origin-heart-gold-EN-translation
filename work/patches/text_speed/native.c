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
static inline unsigned mode(void) {
    void *save=FN(0x02001195,void *(*)(void))();
    /* This accessor uses the main runtime pointer, published at 0x02000cda
     * only after SaveData construction, block metadata and Options init/load
     * have completed. Before publication it is null. The earlier internal
     * constructor pointer is a different global and must not be used here.
     * SaveData + 4 means a cartridge save exists, not runtime readiness:
     * fresh games have initialized Options while that flag is still zero. */
    if (!save) return 3;
    u16 *opts=FN(0x02029349,u16 *(*)(void *))(save);
    if (!opts) return 3;
    unsigned m=(*opts>>2)&3;
    return m;
}
/* Constructor storage grows from 0x34 to 0x38 bytes. The original initializer
 * still owns +0x30; only our extension byte +0x34 stores the SLOW phase.
 * Each newly allocated printer starts independently, including reused heap slots. */
void init_printer(void *p) {
    FN(0x02020be9,void (*)(void *))(p);
    U8(p,0x34)=0;
}
/* Preserve special pacing and callbacks. Invalid/unpublished options use the
 * original renderer; ordinary SLOW/MEDIUM/FAST use bounded glyph batches. */
void print_task(void *task, void *p) {
    unsigned m=mode();
    if (m==3 || U32(p,0x1c) || (U8(p,0x29)&127)) {
        FN(0x02020a1d,void (*)(void *,void *))(task,p); return;
    }
    if (*(volatile u8 *)0x021d0ef4) return;
    unsigned budget=m==0?1+(U8(p,0x34)&1):m+1;
    unsigned dirty=0;
    FN(0x02020a9d,void (*)(unsigned,unsigned,unsigned))(U8(p,0x15),U8(p,0x16),U8(p,0x17));
    do {
        U16(p,0x2e)=0;
        unsigned result=FN(0x02020a89,unsigned (*)(void *))(p);
        if (result==0) dirty=1;
        if (result==1) {
            if(dirty) FN(0x0201dda9,void (*)(void *))((void *)U32(p,4));
            FN(0x0202075d,void (*)(unsigned))(U8(p,0x2c)); return;
        }
        if(result!=0 || U8(p,0x28) || U8(p,0x2a)) break;
        u16 next=*(u16 *)U32(p,0);
        /* Stop before every non-glyph control, including extended controls.
           Newline is handled by the native RenderFont repeat dispatcher. */
        if(next==0xffff || next==0xfffe || next==0x25bc || next==0x25bd || next==0xf0fd) break;
    } while(--budget);
    if(dirty) {
        if(m==0) U8(p,0x34)^=1;
        FN(0x0201dda9,void (*)(void *))((void *)U32(p,4));
    }
}
/* Music still uses the low two bits. Text speed lives in the upper two bits
 * of the historical four-bit music field. Other settings are untouched. */
void load_rows(void *d) {
    FN(0x021e5335,void (*)(void *))(d);
    unsigned m=(U16((void *)U32(d,0x24),0)>>2)&3;
    U16(d,0x27e)=m<3?m:1;
    U16(d,0x2d2)=0;
}
void *load_choice(void *msg,unsigned id) {
    if(id>=41 && id<=43) {
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
        unsigned m=U16(d,0x27e);
        if(m>2) m=1;
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
