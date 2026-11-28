// 12비트 부호 있는 덧셈기 (게이트 확인용 주석)
module adder12 (
    input  wire signed [11:0] A,
    input  wire signed [11:0] B,

    output wire signed [11:0] SUM
);

    assign SUM = A + B;

endmodule
