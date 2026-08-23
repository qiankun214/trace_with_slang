//==============================================================================
// Module:    byte_swapper
// Level:     3 (leaf module, instantiated inside data_transform)
// Description: 4 字节大小端交换单元
//              模块内部定义局部 struct 类型 swap_word_t 用于内部信号声明。
//              纯组合逻辑。
//
// struct 场景：struct 直接定义在模块内部（swap_word_t）
//==============================================================================

module byte_swapper (
    input  logic [31:0] word_in,
    output logic [31:0] word_out
);

    //---- 模块内部定义局部 struct 类型 ---------------------------------------
    // swap_word_t 用于将 32-bit 字拆分为 4 个独立字节进行处理
    typedef struct packed {
        logic [7:0] byte0;      // 最低有效字节
        logic [7:0] byte1;
        logic [7:0] byte2;
        logic [7:0] byte3;      // 最高有效字节
    } swap_word_t;

    //---- 内部信号（使用局部定义的 struct 类型）-------------------------------
    swap_word_t in_bytes;
    swap_word_t out_bytes;

    //---- 输入端 struct 赋值 -------------------------------------------------
    always_comb begin
        in_bytes = swap_word_t'(word_in);
    end

    //---- 字节序反转 ---------------------------------------------------------
    // 将 byte0↔byte3, byte1↔byte2 交换，实现大端↔小端转换
    always_comb begin
        out_bytes.byte0 = in_bytes.byte3;
        out_bytes.byte1 = in_bytes.byte2;
        out_bytes.byte2 = in_bytes.byte1;
        out_bytes.byte3 = in_bytes.byte0;
    end

    //---- 输出端 struct 还原 -------------------------------------------------
    assign word_out = out_bytes;

endmodule
