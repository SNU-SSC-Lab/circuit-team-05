module result_tx (
    input  wire        CLK,
    input  wire        RST_N,

    input  wire        LOAD,
    input  wire [15:0] RESULT_DATA,

    output wire [3:0]  OUT,
    output wire        OUT_VALID,
    output wire        DONE
);

    reg [15:0] result_shift;
    reg [1:0]  nibble_index;
    reg        busy;

    // 하위 nibble부터 출력
    assign OUT       = busy ? result_shift[3:0] : 4'h0;
    assign OUT_VALID = busy;

    // 마지막 nibble이 수신되는 상승 에지에서
    // controller도 완료를 확인하도록 조합 신호로 생성
    assign DONE = busy && (nibble_index == 2'd3);

    // 동기식 active-low reset
    always @(posedge CLK) begin
        if (!RST_N) begin
            result_shift <= 16'h0000;
            nibble_index <= 2'd0;
            busy         <= 1'b0;
        end
        else if (LOAD) begin
            // 마지막 항까지 반영된 결과 저장
            result_shift <= RESULT_DATA;
            nibble_index <= 2'd0;
            busy         <= 1'b1;
        end
        else if (busy) begin
            if (nibble_index == 2'd3) begin
                // 마지막 nibble 전송 완료
                result_shift <= 16'h0000;
                nibble_index <= 2'd0;
                busy         <= 1'b0;
            end
            else begin
                result_shift <= {4'h0, result_shift[15:4]};
                nibble_index <= nibble_index + 2'd1;
            end
        end
    end

endmodule