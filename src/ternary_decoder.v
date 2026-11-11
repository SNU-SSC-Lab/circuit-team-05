module ternary_decoder(
    input wire [1:0] CODE,
    output wire ACTIVE,
    output wire NEGATE,
    output wire ILLEGAL
);
    assign ACTIVE = CODE[1] ^ CODE[0];
    assign NEGATE = CODE[1];
    assign ILLEGAL = CODE[1] & CODE[0];
endmodule