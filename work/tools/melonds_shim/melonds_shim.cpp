// SPDX-License-Identifier: GPL-3.0-or-later
// melonds_shim - a small C API over the melonDS 1.1 core for the emulator harness (work/tools/melonds.py).
//
// Copyright (C) 2026 the Origin HeartGold English translation project.
// This file links against melonDS (GPLv3) and is distributed under the GNU General Public License,
// version 3 or (at your option) any later version. See LICENSE.md in this folder.
//
// Written for this project against the public headers of the official melonDS 1.1 release
// (https://github.com/melonDS-emu/melonDS, tag 1.1). No melonDS source is copied here; the core is
// built from a pinned checkout (build.py) and linked statically into libmelonds_shim.dylib.
//
// What it adds on top of the core, without changing it:
//   - Platform callbacks (file I/O, threads, logging, save write-back) for a headless process;
//   - a subclass of melonDS::NDS that overrides the virtual ARM9 bus accessors to record data
//     watchpoint hits (CPU loads/stores that leave the TCMs, and ARM9 DMA);
//   - capture of the core's ARM9 exception log lines (data abort, prefetch abort, undefined
//     instruction) as counters, so a scenario can detect the abort loop without a debugger.
// There is no per-instruction hook: the interpreter's loop is not virtual and the only stock hook
// (the GDB stub) blocks on a socket. See work/notes/melonds_backend.md.

#include <atomic>
#include <chrono>
#include <condition_variable>
#include <cstdarg>
#include <cstdio>
#include <cstring>
#include <deque>
#include <memory>
#include <mutex>
#include <string>
#include <thread>
#include <vector>

#include "NDS.h"
#include "NDSCart.h"
#include "Platform.h"
#include "Savestate.h"
#include "GPU3D_Soft.h"
#include "Args.h"

using namespace melonDS;

#define MDS_API extern "C" __attribute__((visibility("default")))
#define MDS_ABI_VERSION 1

namespace {

struct Hit {
    uint32_t addr, size, value, is_write, r15, cpsr, frame, _pad;
};

struct Watch {
    uint64_t start, end;   // [start, end), 64-bit so start + length cannot wrap
    uint32_t kinds;        // bit 0 read, bit 1 write
};

struct Instance;
thread_local Instance* g_current = nullptr;

class HookedNDS;

struct Instance {
    std::unique_ptr<HookedNDS> nds;
    std::string rom_name;
    std::vector<uint8_t> state;          // last savestate made by mds_savestate_save
    uint32_t frame = 0;
    uint32_t keys_pressed = 0;
    // ARM9 exception log capture
    uint32_t data_aborts = 0, prefetch_aborts = 0, undefined = 0;
    uint32_t first_data_abort_r15 = 0, first_data_abort_frame = 0, last_data_abort_r15 = 0;
    uint32_t first_prefetch_r15 = 0, first_undefined_addr = 0;
    uint32_t save_writes = 0, last_save_write_frame = 0;
    bool stopped = false;
    int stop_reason = -1;
    // watchpoints
    std::vector<Watch> watches;
    std::vector<Hit> hits;
    uint32_t hits_dropped = 0;
    uint32_t hit_capacity = 4096;
    // log ring
    std::deque<std::string> log;
    int log_echo = 0;  // 1: also print core log lines to stderr
};

class HookedNDS final : public NDS {
public:
    HookedNDS(NDSArgs&& args, Instance* inst) : NDS(std::move(args), inst), Inst(inst) {}

    // The core leaves some members uninitialised (RTC I/O state, Wifi, GPU2D and ARM fields), so a fresh console
    // would start from whatever the heap held and two instances or processes could diverge. Zero the object
    // before construction so every run starts from the same bytes.
    static void* operator new(size_t n) {
        void* p = ::operator new(n);
        std::memset(p, 0, n);
        return p;
    }
    static void operator delete(void* p) { ::operator delete(p); }

    void Record(uint32_t addr, uint32_t size, uint32_t value, bool write) {
        Instance* in = Inst;
        uint32_t kind = write ? 2u : 1u;
        for (const Watch& w : in->watches) {
            if ((w.kinds & kind) && addr < w.end && (uint64_t)addr + size > w.start) {
                if (in->hits.size() < in->hit_capacity)
                    in->hits.push_back({addr, size, value, write ? 1u : 0u, ARM9.R[15], ARM9.CPSR, in->frame, 0});
                else
                    in->hits_dropped++;
                return;
            }
        }
    }

    u8 ARM9Read8(u32 addr) override {
        u8 v = NDS::ARM9Read8(addr);
        if (!Inst->watches.empty()) Record(addr, 1, v, false);
        return v;
    }
    u16 ARM9Read16(u32 addr) override {
        u16 v = NDS::ARM9Read16(addr);
        if (!Inst->watches.empty()) Record(addr & ~1u, 2, v, false);
        return v;
    }
    u32 ARM9Read32(u32 addr) override {
        u32 v = NDS::ARM9Read32(addr);
        if (!Inst->watches.empty()) Record(addr & ~3u, 4, v, false);
        return v;
    }
    void ARM9Write8(u32 addr, u8 val) override {
        if (!Inst->watches.empty()) Record(addr, 1, val, true);
        NDS::ARM9Write8(addr, val);
    }
    void ARM9Write16(u32 addr, u16 val) override {
        if (!Inst->watches.empty()) Record(addr & ~1u, 2, val, true);
        NDS::ARM9Write16(addr, val);
    }
    void ARM9Write32(u32 addr, u32 val) override {
        if (!Inst->watches.empty()) Record(addr & ~3u, 4, val, true);
        NDS::ARM9Write32(addr, val);
    }

    Instance* Inst;
};

void note_log_line(Instance* in, const char* line) {
    unsigned v = 0;
    if (std::sscanf(line, "ARM9: data abort (%08X)", &v) == 1) {
        if (in->data_aborts++ == 0) {
            in->first_data_abort_r15 = v;
            in->first_data_abort_frame = in->frame;
        }
        in->last_data_abort_r15 = v;
    } else if (std::sscanf(line, "ARM9: prefetch abort (%08X)", &v) == 1) {
        if (in->prefetch_aborts++ == 0) in->first_prefetch_r15 = v;
    } else {
        unsigned instr = 0, at = 0;
        if (std::sscanf(line, "undefined ARM9 instruction %08X @ %08X", &instr, &at) == 2 ||
            std::sscanf(line, "undefined THUMB9 instruction %04X @ %08X", &instr, &at) == 2) {
            if (in->undefined++ == 0) in->first_undefined_addr = at;
        }
    }
    if (in->log.size() >= 256) in->log.pop_front();
    in->log.emplace_back(line);
    if (in->log_echo) std::fputs(line, stderr);
}

bool tcm_read(NDS& nds, uint32_t addr, uint8_t* out) {
    ARMv5& a = nds.ARM9;
    if (addr < a.ITCMSize) { *out = a.ITCM[addr & (ITCMPhysicalSize - 1)]; return true; }
    if ((addr & a.DTCMMask) == a.DTCMBase) { *out = a.DTCM[addr & (DTCMPhysicalSize - 1)]; return true; }
    return false;
}

bool tcm_write(NDS& nds, uint32_t addr, uint8_t v) {
    ARMv5& a = nds.ARM9;
    if (addr < a.ITCMSize) { a.ITCM[addr & (ITCMPhysicalSize - 1)] = v; return true; }
    if ((addr & a.DTCMMask) == a.DTCMBase) { a.DTCM[addr & (DTCMPhysicalSize - 1)] = v; return true; }
    return false;
}

} // namespace

// ------------------------------------------------------------------------------------------------ Platform
namespace melonDS::Platform {

void SignalStop(StopReason reason, void* userdata) {
    auto* in = static_cast<Instance*>(userdata);
    if (in) { in->stopped = true; in->stop_reason = (int)reason; }
}

static FILE* fp(FileHandle* f) { return reinterpret_cast<FILE*>(f); }

std::string GetLocalFilePath(const std::string& filename) { return filename; }

FileHandle* OpenFile(const std::string& path, FileMode mode) {
    if ((mode & FileMode::ReadWrite) == FileMode::None) return nullptr;
    std::string m;
    bool exists = FileExists(path);
    if ((mode & FileMode::Write) && (mode & FileMode::NoCreate) && !exists) return nullptr;
    if (mode & FileMode::Append) m = (mode & FileMode::Read) ? "a+" : "a";
    else if (mode & FileMode::Write) {
        if ((mode & FileMode::Preserve) && exists) m = "r+";
        else m = (mode & FileMode::Read) ? "w+" : "w";
    } else m = "r";
    if (!(mode & FileMode::Text)) m += "b";
    return reinterpret_cast<FileHandle*>(std::fopen(path.c_str(), m.c_str()));
}

FileHandle* OpenLocalFile(const std::string& path, FileMode mode) { return OpenFile(path, mode); }
bool FileExists(const std::string& name) {
    FILE* f = std::fopen(name.c_str(), "rb");
    if (!f) return false;
    std::fclose(f);
    return true;
}
bool LocalFileExists(const std::string& name) { return FileExists(name); }
bool CheckFileWritable(const std::string& filepath) {
    FILE* f = std::fopen(filepath.c_str(), "ab");
    if (!f) return false;
    std::fclose(f);
    return true;
}
bool CheckLocalFileWritable(const std::string& filepath) { return CheckFileWritable(filepath); }
bool CloseFile(FileHandle* file) { return std::fclose(fp(file)) == 0; }
bool IsEndOfFile(FileHandle* file) { return std::feof(fp(file)) != 0; }
bool FileReadLine(char* str, int count, FileHandle* file) { return std::fgets(str, count, fp(file)) != nullptr; }
u64 FilePosition(FileHandle* file) { return (u64)std::ftell(fp(file)); }
bool FileSeek(FileHandle* file, s64 offset, FileSeekOrigin origin) {
    int w = origin == FileSeekOrigin::Start ? SEEK_SET : origin == FileSeekOrigin::Current ? SEEK_CUR : SEEK_END;
    return std::fseek(fp(file), (long)offset, w) == 0;
}
void FileRewind(FileHandle* file) { std::rewind(fp(file)); }
u64 FileRead(void* data, u64 size, u64 count, FileHandle* file) { return std::fread(data, size, count, fp(file)); }
bool FileFlush(FileHandle* file) { return std::fflush(fp(file)) == 0; }
u64 FileWrite(const void* data, u64 size, u64 count, FileHandle* file) {
    return std::fwrite(data, size, count, fp(file));
}
u64 FileWriteFormatted(FileHandle* file, const char* fmt, ...) {
    va_list args;
    va_start(args, fmt);
    int n = std::vfprintf(fp(file), fmt, args);
    va_end(args);
    return n < 0 ? 0 : (u64)n;
}
u64 FileLength(FileHandle* file) {
    FILE* f = fp(file);
    long pos = std::ftell(f);
    std::fseek(f, 0, SEEK_END);
    long len = std::ftell(f);
    std::fseek(f, pos, SEEK_SET);
    return (u64)len;
}

void Log(LogLevel level, const char* fmt, ...) {
    char buf[1024];
    va_list args;
    va_start(args, fmt);
    std::vsnprintf(buf, sizeof buf, fmt, args);
    va_end(args);
    if (g_current) note_log_line(g_current, buf);
    else if (level >= LogLevel::Warn) std::fputs(buf, stderr);
}

// Threads: the software 3D renderer runs unthreaded here, but the core may still ask.
struct ThreadImpl { std::thread t; };
Thread* Thread_Create(std::function<void()> func) {
    auto* t = new ThreadImpl{std::thread(std::move(func))};
    return reinterpret_cast<Thread*>(t);
}
void Thread_Free(Thread* thread) {
    auto* t = reinterpret_cast<ThreadImpl*>(thread);
    if (t->t.joinable()) t->t.detach();
    delete t;
}
void Thread_Wait(Thread* thread) {
    auto* t = reinterpret_cast<ThreadImpl*>(thread);
    if (t->t.joinable()) t->t.join();
}

struct SemaImpl { std::mutex m; std::condition_variable cv; int count = 0; };
Semaphore* Semaphore_Create() { return reinterpret_cast<Semaphore*>(new SemaImpl); }
void Semaphore_Free(Semaphore* s) { delete reinterpret_cast<SemaImpl*>(s); }
void Semaphore_Reset(Semaphore* s) {
    auto* x = reinterpret_cast<SemaImpl*>(s);
    std::lock_guard<std::mutex> l(x->m);
    x->count = 0;
}
void Semaphore_Wait(Semaphore* s) {
    auto* x = reinterpret_cast<SemaImpl*>(s);
    std::unique_lock<std::mutex> l(x->m);
    x->cv.wait(l, [x] { return x->count > 0; });
    x->count--;
}
bool Semaphore_TryWait(Semaphore* s, int timeout_ms) {
    auto* x = reinterpret_cast<SemaImpl*>(s);
    std::unique_lock<std::mutex> l(x->m);
    if (!x->cv.wait_for(l, std::chrono::milliseconds(timeout_ms), [x] { return x->count > 0; })) return false;
    x->count--;
    return true;
}
void Semaphore_Post(Semaphore* s, int count) {
    auto* x = reinterpret_cast<SemaImpl*>(s);
    {
        std::lock_guard<std::mutex> l(x->m);
        x->count += count;
    }
    x->cv.notify_all();
}

Mutex* Mutex_Create() { return reinterpret_cast<Mutex*>(new std::mutex); }
void Mutex_Free(Mutex* m) { delete reinterpret_cast<std::mutex*>(m); }
void Mutex_Lock(Mutex* m) { reinterpret_cast<std::mutex*>(m)->lock(); }
void Mutex_Unlock(Mutex* m) { reinterpret_cast<std::mutex*>(m)->unlock(); }
bool Mutex_TryLock(Mutex* m) { return reinterpret_cast<std::mutex*>(m)->try_lock(); }

void Sleep(u64 usecs) { std::this_thread::sleep_for(std::chrono::microseconds(usecs)); }
u64 GetMSCount() {
    return (u64)std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::steady_clock::now().time_since_epoch()).count();
}
u64 GetUSCount() {
    return (u64)std::chrono::duration_cast<std::chrono::microseconds>(
        std::chrono::steady_clock::now().time_since_epoch()).count();
}

// The cart keeps its own save memory; the shim only counts the writes (mds_save_read exports it).
void WriteNDSSave(const u8*, u32, u32, u32, void* userdata) {
    auto* in = static_cast<Instance*>(userdata);
    if (in) { in->save_writes++; in->last_save_write_frame = in->frame; }
}
void WriteGBASave(const u8*, u32, u32, u32, void*) {}
void WriteFirmware(const Firmware&, u32, u32, void*) {}
void WriteDateTime(int, int, int, int, int, int, void*) {}

void MP_Begin(void*) {}
void MP_End(void*) {}
int MP_SendPacket(u8*, int, u64, void*) { return 0; }
int MP_RecvPacket(u8*, u64*, void*) { return 0; }
int MP_SendCmd(u8*, int, u64, void*) { return 0; }
int MP_SendReply(u8*, int, u64, u16, void*) { return 0; }
int MP_SendAck(u8*, int, u64, void*) { return 0; }
int MP_RecvHostPacket(u8*, u64*, void*) { return 0; }
u16 MP_RecvReplies(u8*, u64, u16, void*) { return 0; }
int Net_SendPacket(u8*, int len, void*) { return len; }
int Net_RecvPacket(u8*, void*) { return 0; }

void Camera_Start(int, void*) {}
void Camera_Stop(int, void*) {}
void Camera_CaptureFrame(int, u32* frame, int width, int height, bool yuv, void*) {
    // YUV frames pack two pixels per u32
    std::memset(frame, 0, (size_t)(yuv ? width / 2 : width) * height * 4);
}
void Mic_Start(void*) {}
void Mic_Stop(void*) {}
int Mic_ReadInput(s16*, int, void*) { return 0; }

AACDecoder* AAC_Init() { return nullptr; }
void AAC_DeInit(AACDecoder*) {}
bool AAC_Configure(AACDecoder*, int, int) { return false; }
bool AAC_DecodeFrame(AACDecoder*, const void*, int, void*, int) { return false; }

bool Addon_KeyDown(KeyType, void*) { return false; }
void Addon_RumbleStart(u32, void*) {}
void Addon_RumbleStop(void*) {}
float Addon_MotionQuery(MotionQueryType, void*) { return 0.0f; }

DynamicLibrary* DynamicLibrary_Load(const char*) { return nullptr; }
void DynamicLibrary_Unload(DynamicLibrary*) {}
void* DynamicLibrary_LoadFunction(DynamicLibrary*, const char*) { return nullptr; }

} // namespace melonDS::Platform

// ------------------------------------------------------------------------------------------------ C API
namespace {
struct Current {
    explicit Current(Instance* in) : prev(g_current) { g_current = in; }
    ~Current() { g_current = prev; }
    Instance* prev;
};

bool read_file(const char* path, std::unique_ptr<u8[]>& data, u32& len) {
    FILE* f = std::fopen(path, "rb");
    if (!f) return false;
    std::fseek(f, 0, SEEK_END);
    long n = std::ftell(f);
    std::fseek(f, 0, SEEK_SET);
    if (n <= 0) { std::fclose(f); return false; }
    data = std::make_unique<u8[]>((size_t)n);
    bool ok = std::fread(data.get(), 1, (size_t)n, f) == (size_t)n;
    std::fclose(f);
    len = (u32)n;
    return ok;
}

void apply_keys(Instance* in) {
    // shim bits: 0 A, 1 B, 2 SELECT, 3 START, 4 RIGHT, 5 LEFT, 6 UP, 7 DOWN, 8 R, 9 L, 10 X, 11 Y (1 = pressed);
    // the core's mask is active low with the same order.
    in->nds->SetKeyMask(~in->keys_pressed & 0xFFF);
}
} // namespace

MDS_API int mds_abi_version(void) { return MDS_ABI_VERSION; }
MDS_API const char* mds_melonds_version(void) { return "1.1"; }

MDS_API Instance* mds_create(void) {
    auto* in = new Instance();
    Current c(in);
    NDSArgs args;               // FreeBIOS (built-in), generated firmware, software 3D renderer
    args.JIT = std::nullopt;
    in->nds = std::make_unique<HookedNDS>(std::move(args), in);
    in->nds->Reset();           // memory map (MainRAMMask, TCMs) is set up by Reset, not the constructor
    return in;
}

MDS_API void mds_destroy(Instance* in) {
    if (!in) return;
    {
        Current c(in);
        in->nds.reset();
    }
    delete in;
}

MDS_API void mds_set_log_echo(Instance* in, int echo) { in->log_echo = echo; }

// Load a ROM file and an optional battery save (sav may be NULL), reset and boot. direct_boot: 1 starts the
// game's code directly (needed with the built-in FreeBIOS). Returns 1 on success.
MDS_API int mds_load_rom(Instance* in, const char* rom_path, const uint8_t* sav, uint32_t savlen, int direct_boot) {
    Current c(in);
    std::unique_ptr<u8[]> rom;
    u32 romlen = 0;
    if (!read_file(rom_path, rom, romlen)) return 0;
    NDSCart::NDSCartArgs cargs;
    if (sav && savlen) {
        cargs.SRAM = std::make_unique<u8[]>(savlen);
        std::memcpy(cargs.SRAM.get(), sav, savlen);
        cargs.SRAMLength = savlen;
    }
    auto cart = NDSCart::ParseROM(std::move(rom), romlen, in, std::move(cargs));
    if (!cart) return 0;
    std::string p(rom_path);
    size_t slash = p.find_last_of('/');
    in->rom_name = slash == std::string::npos ? p : p.substr(slash + 1);
    in->nds->SetNDSCart(std::move(cart));
    in->nds->Reset();
    if (direct_boot || in->nds->NeedsDirectBoot()) in->nds->SetupDirectBoot(in->rom_name);
    in->nds->Start();
    in->frame = 0;
    in->stopped = false;
    apply_keys(in);
    return 1;
}

// Reset the console with the inserted cart; its save memory is kept (like a power cycle).
MDS_API void mds_reset(Instance* in, int direct_boot) {
    Current c(in);
    in->nds->Reset();
    if (direct_boot || in->nds->NeedsDirectBoot()) in->nds->SetupDirectBoot(in->rom_name);
    in->nds->Start();
    in->stopped = false;
    apply_keys(in);
}

MDS_API void mds_set_rtc(Instance* in, int year, int month, int day, int hour, int minute, int second) {
    Current c(in);
    in->nds->RTC.SetDateTime(year, month, day, hour, minute, second);
}

MDS_API uint32_t mds_run_frame(Instance* in) {
    Current c(in);
    u32 lines = in->nds->RunFrame();
    // drain audio so the output ring never matters for timing
    static thread_local s16 sink[2 * 2048];
    while (in->nds->SPU.GetOutputSize() > 0)
        if (in->nds->SPU.ReadOutput(sink, 2048) <= 0) break;
    in->frame++;
    return lines;
}

MDS_API uint32_t mds_frame(Instance* in) { return in->frame; }
MDS_API int mds_stopped(Instance* in) { return in->stopped ? 1 + in->stop_reason : 0; }

MDS_API void mds_set_keys(Instance* in, uint32_t pressed) {
    in->keys_pressed = pressed & 0xFFF;
    apply_keys(in);
}

MDS_API void mds_touch(Instance* in, int x, int y) { in->nds->TouchScreen((u16)x, (u16)y); }
MDS_API void mds_release_touch(Instance* in) { in->nds->ReleaseScreen(); }

// 256x384 RGB (top screen, then bottom screen), 3 bytes per pixel.
MDS_API int mds_screenshot_rgb(Instance* in, uint8_t* out) {
    int front = in->nds->GPU.FrontBuffer;
    for (int s = 0; s < 2; s++) {
        const u32* fb = in->nds->GPU.Framebuffer[front][s].get();
        uint8_t* o = out + (size_t)s * 256 * 192 * 3;
        if (!fb) { std::memset(o, 0, 256 * 192 * 3); continue; }
        for (int i = 0; i < 256 * 192; i++) {
            u32 p = fb[i];               // 0xAARRGGBB, 8 bits per channel
            o[3 * i + 0] = (p >> 16) & 0xFF;
            o[3 * i + 1] = (p >> 8) & 0xFF;
            o[3 * i + 2] = p & 0xFF;
        }
    }
    return 1;
}

// Read n bytes as the ARM9 sees them (ITCM, DTCM, then the bus without side-effect free guarantees for I/O).
MDS_API void mds_read(Instance* in, uint32_t addr, uint8_t* out, uint32_t n) {
    Current c(in);
    NDS& nds = *in->nds;
    for (uint32_t i = 0; i < n; i++) {
        uint32_t a = addr + i;
        if (!tcm_read(nds, a, &out[i])) out[i] = nds.NDS::ARM9Read8(a);
    }
}

MDS_API void mds_write(Instance* in, uint32_t addr, const uint8_t* data, uint32_t n) {
    Current c(in);
    NDS& nds = *in->nds;
    for (uint32_t i = 0; i < n; i++) {
        uint32_t a = addr + i;
        if (!tcm_write(nds, a, data[i])) nds.NDS::ARM9Write8(a, data[i]);
    }
}

// Main RAM direct (offset into the 4 MB main memory, mirrored).
MDS_API void mds_read_main_ram(Instance* in, uint32_t offset, uint8_t* out, uint32_t n) {
    NDS& nds = *in->nds;
    for (uint32_t i = 0; i < n; i++) out[i] = nds.MainRAM[(offset + i) & nds.MainRAMMask];
}

MDS_API void mds_write_main_ram(Instance* in, uint32_t offset, const uint8_t* data, uint32_t n) {
    NDS& nds = *in->nds;
    for (uint32_t i = 0; i < n; i++) nds.MainRAM[(offset + i) & nds.MainRAMMask] = data[i];
}

// CPU registers. cpu 0 = ARM9, 1 = ARM7. out[0..15] R0-R15 (R15 = executing instruction + 8 ARM / + 4 Thumb
// between instructions), out[16] CPSR, out[17..19] R_ABT (SP, LR, SPSR banked while not in abort mode),
// out[20..22] R_SVC, out[23..25] R_IRQ, out[26..28] R_UND, out[29] CurInstr, out[30] halted.
MDS_API void mds_cpu_regs(Instance* in, int cpu, uint32_t* out) {
    ARM& a = cpu ? static_cast<ARM&>(in->nds->ARM7) : static_cast<ARM&>(in->nds->ARM9);
    for (int i = 0; i < 16; i++) out[i] = a.R[i];
    out[16] = a.CPSR;
    for (int i = 0; i < 3; i++) {
        out[17 + i] = a.R_ABT[i];
        out[20 + i] = a.R_SVC[i];
        out[23 + i] = a.R_IRQ[i];
        out[26 + i] = a.R_UND[i];
    }
    out[29] = a.CurInstr;
    out[30] = a.Halted;
}

MDS_API void mds_set_cpu_reg(Instance* in, int cpu, int reg, uint32_t value) {
    ARM& a = cpu ? static_cast<ARM&>(in->nds->ARM7) : static_cast<ARM&>(in->nds->ARM9);
    if (reg >= 0 && reg < 15) a.R[reg] = value;
}

// out[0] data aborts, [1] R15 at the first, [2] frame of the first, [3] R15 at the last, [4] prefetch aborts,
// [5] R15 at the first, [6] undefined instructions (ARM9), [7] address of the first,
// [8] battery save writes, [9] frame of the last one.
MDS_API void mds_exceptions(Instance* in, uint32_t* out) {
    out[0] = in->data_aborts; out[1] = in->first_data_abort_r15; out[2] = in->first_data_abort_frame;
    out[3] = in->last_data_abort_r15; out[4] = in->prefetch_aborts; out[5] = in->first_prefetch_r15;
    out[6] = in->undefined; out[7] = in->first_undefined_addr;
    out[8] = in->save_writes; out[9] = in->last_save_write_frame;
}

MDS_API void mds_clear_exceptions(Instance* in) {
    in->data_aborts = in->prefetch_aborts = in->undefined = 0;
    in->first_data_abort_r15 = in->first_data_abort_frame = in->last_data_abort_r15 = 0;
    in->first_prefetch_r15 = in->first_undefined_addr = 0;
}

// Copy the oldest log lines (newline-terminated) into buf and drop them; returns bytes written.
MDS_API uint32_t mds_log_drain(Instance* in, char* buf, uint32_t cap) {
    uint32_t used = 0;
    while (!in->log.empty()) {
        const std::string& s = in->log.front();
        if (used + s.size() + 1 > cap) break;
        std::memcpy(buf + used, s.data(), s.size());
        used += (uint32_t)s.size();
        if (s.empty() || s.back() != '\n') buf[used++] = '\n';
        in->log.pop_front();
    }
    if (used < cap) buf[used] = 0;
    return used;
}

// Data watchpoints on the ARM9 bus. kinds: 1 read, 2 write, 3 both. Accesses served by ITCM/DTCM never reach
// the bus and are not seen. ARM9 DMA transfers are seen too; their hits carry the CPU's R15/CPSR at the time of
// the transfer, not the code that started it.
MDS_API int mds_watch_add(Instance* in, uint32_t start, uint32_t length, uint32_t kinds) {
    if (!length || !(kinds & 3)) return 0;
    in->watches.push_back({start, (uint64_t)start + length, kinds & 3});
    return (int)in->watches.size();
}
MDS_API void mds_watch_clear(Instance* in) { in->watches.clear(); }
MDS_API void mds_watch_capacity(Instance* in, uint32_t capacity) { in->hit_capacity = capacity; }
// Copy up to max hits (8 u32 each: addr, size, value, is_write, R15, CPSR, frame, 0) and drop them.
// Returns the number copied; *dropped receives the hits lost to a full buffer since the last call.
MDS_API uint32_t mds_watch_hits(Instance* in, uint32_t* out, uint32_t max, uint32_t* dropped) {
    uint32_t n = (uint32_t)std::min<size_t>(max, in->hits.size());
    std::memcpy(out, in->hits.data(), (size_t)n * sizeof(Hit));
    in->hits.erase(in->hits.begin(), in->hits.begin() + n);
    if (dropped) { *dropped = in->hits_dropped; in->hits_dropped = 0; }
    return n;
}

// Savestates (melonDS's own format, same as the frontend's .mlN files of version 1.1).
// mds_savestate_save keeps the state inside the instance and returns its length (0 on error);
// mds_savestate_copy copies it out.
MDS_API uint32_t mds_savestate_save(Instance* in) {
    Current c(in);
    Savestate st;
    if (st.Error) return 0;
    in->nds->DoSavestate(&st);
    if (st.Error) return 0;
    st.Finish();
    const u8* b = static_cast<const u8*>(st.Buffer());
    in->state.assign(b, b + st.Length());
    return (uint32_t)in->state.size();
}

MDS_API uint32_t mds_savestate_copy(Instance* in, uint8_t* out, uint32_t cap) {
    uint32_t n = (uint32_t)std::min<size_t>(cap, in->state.size());
    std::memcpy(out, in->state.data(), n);
    return n;
}

MDS_API int mds_savestate_load(Instance* in, const uint8_t* data, uint32_t len) {
    Current c(in);
    std::vector<u8> copy(data, data + len);
    Savestate st(copy.data(), len, false);
    if (st.Error) return 0;
    if (!in->nds->DoSavestate(&st) || st.Error) return 0;
    apply_keys(in);
    return 1;
}

// Battery save memory of the inserted cart.
MDS_API uint32_t mds_save_length(Instance* in) {
    auto* cart = in->nds->GetNDSCart();
    return cart ? cart->GetSaveMemoryLength() : 0;
}
MDS_API uint32_t mds_save_read(Instance* in, uint8_t* out, uint32_t cap) {
    auto* cart = in->nds->GetNDSCart();
    if (!cart || !cart->GetSaveMemory()) return 0;
    uint32_t n = std::min(cap, cart->GetSaveMemoryLength());
    std::memcpy(out, cart->GetSaveMemory(), n);
    return n;
}
// Replace the battery save memory (takes effect for the game's next flash read; use before a reset).
MDS_API void mds_save_write(Instance* in, const uint8_t* data, uint32_t len) {
    Current c(in);
    in->nds->SetNDSSave(data, len);
}
