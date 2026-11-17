module dot8_controller (
    input  wire CLK,
    input  wire RST_N,

    input  wire BYTE_VALID,
    input  wire TX_DONE,

    output wire IN_READY,

    output reg  LOAD_W0,
    output reg  LOAD_W1,
    output reg  WEIGHT_SHIFT,

    output reg  WORK_CLEAR,
    output reg  ACC_EN,

    output reg  RESULT_LOAD
);

    localparam [1:0]
        RECV_W0 = 2'd0,
        RECV_W1 = 2'd1,
        RECV_A  = 2'd2,
        OUTPUT  = 2'd3;

    reg [1:0] state;
    reg [1:0] next_state;

    assign IN_READY = !BYTE_VALID
               && ((state == RECV_W0)
                || (state == RECV_W1)
                || (state == RECV_A));

    // 현재 처리할 입력값 번호: 0~7
    reg [2:0] a_index;

    // 상태 및 입력값 번호 저장
    always @(posedge CLK) begin
        if (!RST_N) begin
            state   <= RECV_W0;
            a_index <= 3'd0;
        end
        else begin
            state <= next_state;

            if (state == RECV_W0 && BYTE_VALID) begin
                a_index <= 3'd0;
            end
            else if (state == RECV_A && BYTE_VALID) begin
                if (a_index == 3'd7)
                    a_index <= 3'd0;
                else
                    a_index <= a_index + 3'd1;
            end
        end
    end

    // 다음 상태 및 조합 제어 신호
    always @(*) begin
        next_state   = state;

        LOAD_W0      = 1'b0;
        LOAD_W1      = 1'b0;
        WEIGHT_SHIFT = 1'b0;

        WORK_CLEAR     = 1'b0;
        ACC_EN        = 1'b0;

        RESULT_LOAD = 1'b0;

        case (state)
            RECV_W0: begin
                if (BYTE_VALID) begin
                    LOAD_W0       = 1'b1;
                    WORK_CLEAR     = 1'b1;

                    next_state = RECV_W1;
                end
            end

            RECV_W1: begin
                if (BYTE_VALID) begin
                    LOAD_W1 = 1'b1;

                    next_state = RECV_A;
                end
            end

            RECV_A: begin
                if (BYTE_VALID) begin
                    ACC_EN       = 1'b1;
                    WEIGHT_SHIFT = 1'b1;

                    if (a_index == 3'd7) begin
                        // 마지막 항 계산과 동시에
                        // acc_next 및 illegal_next 저장
                        RESULT_LOAD = 1'b1;

                        next_state = OUTPUT;
                    end
                end
            end

            OUTPUT: begin
                // 출력 완료 전까지 입력 차단
                if (TX_DONE)
                    next_state = RECV_W0;
            end

            default: begin
                next_state = RECV_W0;
            end
        endcase
    end

endmodule
