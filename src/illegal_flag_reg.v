module illegal_flag_reg (
    input  wire CLK,
    input  wire RST_N,
    input  wire EN,
    input  wire ILLEGAL_CODE,

    output reg  FLAG
);

    // 동기식 active-low reset
    // 우선순위: reset → CLEAR → EN → 유지
    always @(posedge CLK) begin
        if (!RST_N)
            FLAG <= 1'b0;
        else if (EN)
            FLAG <= FLAG | ILLEGAL_CODE;
    end

endmodule