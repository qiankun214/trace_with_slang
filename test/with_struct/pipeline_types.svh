//==============================================================================
// File:    pipeline_types.svh
// Description: 数据处理流水线公共类型定义头文件
//
// 集中定义所有模块共用的 packed struct 类型，各模块通过 `include 引入。
//
// 类型清单：
//   pkt_header_t   — 数据包头部（80-bit packed）
//   config_word_t  — 配置控制字（16-bit packed）
//   status_flags_t — 状态标志位（8-bit packed）
//==============================================================================

`ifndef PIPELINE_TYPES_SVH
`define PIPELINE_TYPES_SVH

//---- 数据包头部类型 (80 bits) -----------------------------------------------
typedef struct packed {
    logic [15:0] src_addr;      // 源地址
    logic [15:0] dst_addr;      // 目的地址
    logic [7:0]  pkt_type;      // 包类型
    logic [7:0]  length;        // 有效载荷长度
    logic [31:0] timestamp;     // 时间戳
} pkt_header_t;

//---- 配置控制字类型 (16 bits) -----------------------------------------------
typedef struct packed {
    logic [3:0]  threshold;     // 处理阈值
    logic [1:0]  mode;          // 处理模式：00=直通 01=交换 10=掩码 11=保留
    logic        bypass;        // 旁路使能
    logic [7:0]  mask;          // 数据掩码
    logic        reserved;      // 保留位（补齐 16-bit）
} config_word_t;

//---- 状态标志类型 (8 bits) --------------------------------------------------
typedef struct packed {
    logic        parity_err;    // 奇偶校验错误
    logic        crc_err;       // CRC 校验错误
    logic        overflow;      // 溢出标志
    logic [4:0]  prio_level;   // 优先级级别 (0~31)
} status_flags_t;

//---- 地址类型 (16-bit) — 用于嵌套在其他 struct 中 ------------------------
typedef struct packed {
    logic [3:0]  region;        // 地址区域
    logic [11:0] offset;        // 区域内偏移
} addr_t;

//---- 扩展包头类型 (80-bit) — 内部嵌套 addr_t -----------------------------
// 场景 5：struct 嵌套 — src/dst 成员本身是 addr_t struct
typedef struct packed {
    addr_t       src;           // 嵌套 addr_t：源地址
    addr_t       dst;           // 嵌套 addr_t：目的地址
    logic [7:0]  pkt_type;      // 包类型
    logic [7:0]  length;        // 有效载荷长度
    logic [31:0] timestamp;     // 时间戳
} pkt_ext_header_t;

`endif  // PIPELINE_TYPES_SVH
