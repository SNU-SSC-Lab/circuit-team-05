module weight_shift_reg (
    input  wire        CLK,
    input  wire        RST_N,

    input  wire [7:0]  BYTE_DATA,
    input  wire        LOAD_W0,
    input  wire        LOAD_W1,
    input  wire        SHIFT_EN,

    output reg  [15:0] WEIGHTS
);

    // 동기식 active-low reset
    // 우선순위: reset → W0 저장 → W1 저장 → shift → 유지
    always @(posedge CLK) begin
        if (!RST_N)
            WEIGHTS <= 16'h0000;
        else if (LOAD_W0)
            WEIGHTS[7:0] <= BYTE_DATA;
        else if (LOAD_W1)
            WEIGHTS[15:8] <= BYTE_DATA;
        else if (SHIFT_EN)
            WEIGHTS <= {2'b00, WEIGHTS[15:2]};
    end

endmodule