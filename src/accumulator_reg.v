module accumulator_reg (
    input  wire               CLK,
    input  wire               RST_N,
    input  wire               EN,
    input  wire signed [11:0] D,

    output reg  signed [11:0] Q
);

    // active-low reset
    // reset → CLEAR → EN → 유지
    always @(posedge CLK) begin
        if (!RST_N)
            Q <= 12'sd0;
        else if (EN)
            Q <= D;
    end

endmodule
