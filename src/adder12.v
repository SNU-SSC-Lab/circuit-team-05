module adder12 (
    input  wire signed [11:0] A,
    input  wire signed [11:0] B,

    output wire signed [11:0] SUM
);

    assign SUM = A + B;

endmodule
