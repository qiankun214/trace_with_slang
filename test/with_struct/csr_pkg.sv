//==============================================================================
// csr_pkg.sv — SystemVerilog Package: 集中定义共享结构体类型
// Level: package（非模块，无层次）
// 场景4: 结构体定义在集中的 SV 文件
//
// 本 package 定义 CSR 系统中所有共享的结构体类型，各模块通过
// `import csr_pkg::*;` 引入。包含 packed struct（用于端口和寄存器）
// 以及嵌套结构体（csr_cfg_t 内含 baud_cfg_t + irq_cfg_t）。
//==============================================================================

package csr_pkg;

    // ── 波特率配置（20 bit packed）──────────────────────────────
    typedef struct packed {
        logic [15:0] div;          // [19:4] 分频系数
        logic [2:0]  oversample;   // [3:1]  过采样率
        logic        mode;         // [0]    模式选择 (0=正常, 1=高速)
    } baud_cfg_t;

    // ── 中断配置（7 bit packed）────────────────────────────────
    typedef struct packed {
        logic       en_tx_done;    // [6]    发送完成中断使能
        logic       en_rx_done;    // [5]    接收完成中断使能
        logic       en_err;        // [4]    错误中断使能
        logic [3:0] prio_level;     // [3:0]  中断优先级 (0-15)
    } irq_cfg_t;

    // ── 嵌套结构体：完整 CSR 配置（27 bit packed）─────────────
    // ★ 场景5核心类型：struct 内嵌套 struct
    typedef struct packed {
        baud_cfg_t  baud;          // [26:7]  嵌套: 波特率配置
        irq_cfg_t   irq;           // [6:0]   嵌套: 中断配置
    } csr_cfg_t;

    // ── 状态结构体（5 bit packed）──────────────────────────────
    typedef struct packed {
        logic       tx_busy;       // [4]    发送忙
        logic       rx_ready;      // [3]    接收就绪
        logic [1:0] fifo_level;    // [2:1]  FIFO 水位
        logic       parity_err;    // [0]    奇偶校验错误
    } csr_status_t;

endpackage
