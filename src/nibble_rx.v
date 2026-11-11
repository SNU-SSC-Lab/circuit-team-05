module nibble_rx (
    input  wire       CLK,
    input  wire       RST_N,

    input  wire [3:0] IN,
    input  wire       IN_VALID,
    input  wire       IN_READY,

    output reg  [7:0] BYTE_DATA,
    output reg        BYTE_VALID
);
    reg [3:0] low_nibble;

    reg half_received;

    // 내부가 수신 가능하고,
    // 아직 전달하지 않은 완성 바이트가 없을 때 입력 허용

    always @(posedge CLK) begin
        if (!RST_N) begin
            low_nibble    <= 4'b0000;
            half_received <= 1'b0;
            BYTE_DATA     <= 8'h00;
            BYTE_VALID    <= 1'b0;
        end
        else begin
            BYTE_VALID <= 1'b0;

            if (IN_VALID && IN_READY) begin
                if (!half_received) begin
                    // 첫 번째 nibble: 하위 4비트
                    low_nibble    <= IN;
                    half_received <= 1'b1;
                end
                else begin
                    // 두 번째 nibble: 상위 4비트
                    BYTE_DATA     <= {IN, low_nibble};
                    BYTE_VALID    <= 1'b1;
                    half_received <= 1'b0;
                end
            end
        end
    end

endmodule