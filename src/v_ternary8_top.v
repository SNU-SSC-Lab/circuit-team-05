module v_ternary8_top (
    input  wire       CLK,
    input  wire       RST_N,

    input  wire [3:0] IN,
    input  wire       IN_VALID,
    output wire       IN_READY,

    output wire [3:0] OUT,
    output wire       OUT_VALID
);

    // 입력 바이트 인터페이스
    wire [7:0] byte_data;
    wire       byte_valid;

    // FSM 제어 신호
    wire load_w0;
    wire load_w1;
    wire weight_shift;
    wire work_clear;
    wire acc_en;
    wire result_load;
    wire tx_done;

    wire acc_flag_rst_n;

    assign acc_flag_rst_n = RST_N & ~work_clear;

    // 가중치 및 디코더 출력
    wire [15:0] weights;
    wire        term_active;
    wire        term_negate;
    wire        illegal_code;

    // 연산 데이터 경로
    wire signed [11:0] term;
    wire signed [11:0] acc;
    wire signed [11:0] acc_next;

    // 오류 및 결과 포장
    wire        illegal_weight;
    wire        illegal_next;
    wire [15:0] result_data;

    // 마지막 항에서 발생한 오류까지 반영
    assign illegal_next = illegal_weight | illegal_code;

    // B0 = acc_next[7:0]
    // B1 = {3'b000, illegal_next, acc_next[11:8]}
    assign result_data = {3'b000, illegal_next, acc_next};

    // 1. 하위 nibble → 상위 nibble 순서로 바이트 조립
    nibble_rx u_rx (
        .CLK        (CLK),
        .RST_N      (RST_N),
        .IN         (IN),
        .IN_VALID   (IN_VALID),
        .IN_READY   (IN_READY),
        .BYTE_DATA  (byte_data),
        .BYTE_VALID (byte_valid)
    );

    // 2. W0 → W1 → a0~a7 → 결과 출력 순서 제어
    // 제어 신호는 바이트 전달 에지에 작용하도록 생성
    // a7 처리 시 ACC_EN과 RESULT_LOAD를 함께 활성화
    dot8_controller u_controller (
        .CLK           (CLK),
        .RST_N         (RST_N),
        .BYTE_VALID    (byte_valid),
        .IN_READY      (IN_READY),
        .TX_DONE       (tx_done),
        .LOAD_W0       (load_w0),
        .LOAD_W1       (load_w1),
        .WEIGHT_SHIFT  (weight_shift),
        .WORK_CLEAR     (work_clear),
        .ACC_EN        (acc_en),
        .RESULT_LOAD   (result_load)
    );

    // 3. 가중치 16비트 저장 및 항 처리마다 오른쪽 2비트 이동
    weight_shift_reg u_weights (
        .CLK       (CLK),
        .RST_N     (RST_N),
        .BYTE_DATA (byte_data),
        .LOAD_W0   (load_w0),
        .LOAD_W1   (load_w1),
        .SHIFT_EN  (weight_shift),
        .WEIGHTS   (weights)
    );

    // 4. 가중치 해석
    // 00: 비활성, 01: +a, 10: -a, 11: 비활성 및 오류
    ternary_decoder u_decoder (
        .CODE    (weights[1:0]),
        .ACTIVE  (term_active),
        .NEGATE  (term_negate),
        .ILLEGAL (illegal_code)
    );

    // 5. signed 8→12비트 부호 확장 후 0, +a, -a 생성
    ternary_term u_term (
        .A       (byte_data),
        .ACTIVE  (term_active),
        .NEGATE  (term_negate),
        .TERM    (term)
    );

    // 6. 조합 덧셈: acc_next = acc + term
    adder12 u_adder (
        .A   (acc),
        .B   (term),
        .SUM (acc_next)
    );

    // 7. 누산값 저장
    accumulator_reg u_acc (
        .CLK   (CLK),
        .RST_N (acc_flag_rst_n),
        .EN    (acc_en),
        .D     (acc_next),
        .Q     (acc)
    );

    // 8. 입력값 처리 시 오류 누적, 새 작업에서 초기화
    illegal_flag_reg u_illegal (
        .CLK          (CLK),
        .RST_N        (acc_flag_rst_n),
        .EN           (acc_en),
        .ILLEGAL_CODE (illegal_code),
        .FLAG         (illegal_weight)
    );

    // 9. 최종 결과 저장 후 하위 nibble부터 4회 연속 출력
    result_tx u_tx (
        .CLK         (CLK),
        .RST_N       (RST_N),
        .LOAD        (result_load),
        .RESULT_DATA (result_data),
        .OUT         (OUT),
        .OUT_VALID   (OUT_VALID),
        .DONE        (tx_done)
    );

endmodule