module ternary_term(
    input wire [7:0] A,
    input wire ACTIVE,
    input wire NEGATE,
    output wire signed [11:0] TERM
);
wire signed [11:0] a_ext;

    // signed extension
    assign a_ext = {{4{A[7]}}, A};

    // 0 if ACTIVE = 0
    assign TERM = !ACTIVE ? 12'sd0
                : NEGATE  ? -a_ext
                          :  a_ext;

endmodule