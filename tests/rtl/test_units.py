import os
import cocotb
from cocotb.triggers import Timer
from model import signed
from transport import number, step, write_stats


async def initialize(d, **values):
    for _ in range(4):
        await step(d, RST_N=0, **values)
    await step(d, RST_N=1, **values)


@cocotb.test()
async def unit_contract(d):
    name = os.environ['SSC_DUT']
    samples = 0
    extra = {}
    if name == 'ternary_decoder':
        for c, wanted in enumerate([(0,0,0),(1,0,0),(1,1,0),(0,1,1)]):
            d.CODE.value = c
            await Timer(1, unit='ns')
            assert tuple(number(getattr(d,n)) for n in ('ACTIVE','NEGATE','ILLEGAL')) == wanted
            samples += 1
    elif name == 'ternary_term':
        for a in range(256):
            for c in range(4):
                d.A.value = a
                d.ACTIVE.value = int(c in (1,2))
                d.NEGATE.value = int(c in (2,3))
                await Timer(1, unit='ns')
                assert signed(number(d.TERM),12) == (0,1,-1,0)[c] * signed(a,8)
                samples += 1
    elif name == 'adder12':
        for a in range(4096):
            for b in (0,1,-1,128,-128,2047,-2048):
                d.A.value, d.B.value = a, b & 4095
                await Timer(1, unit='ns')
                assert signed(number(d.SUM),12) == signed(signed(a,12)+b,12)
                samples += 1
    elif name == 'accumulator_reg':
        await initialize(d, EN=0, D=0)
        for value in (0,1,-1,128,-128,2047,-2048):
            await step(d, EN=1, D=value & 4095)
            assert signed(number(d.Q),12) == value
            await step(d, EN=0, D=(value+1)&4095)
            assert signed(number(d.Q),12) == value
            await step(d, RST_N=0, EN=1, D=123)
            assert number(d.Q) == 0
            await step(d, RST_N=1, EN=0)
            samples += 3
    elif name == 'illegal_flag_reg':
        await initialize(d, EN=0, ILLEGAL_CODE=0)
        flag = 0
        for enable, code in [(0,1),(1,0),(1,1),(0,0),(1,0),(1,1)]:
            await step(d, EN=enable, ILLEGAL_CODE=code)
            flag |= code if enable else 0
            assert number(d.FLAG) == flag
            samples += 1
        await step(d, RST_N=0, EN=1, ILLEGAL_CODE=1)
        assert number(d.FLAG) == 0
    elif name == 'weight_shift_reg':
        await initialize(d, BYTE_DATA=0, LOAD_W0=0, LOAD_W1=0, SHIFT_EN=0)
        codes = [1,2,0,3,2,1,3,0]
        value = sum(c << (2*i) for i,c in enumerate(codes))
        await step(d, BYTE_DATA=value&255, LOAD_W0=1, LOAD_W1=1, SHIFT_EN=1)
        assert number(d.WEIGHTS) == value&255
        await step(d, BYTE_DATA=value>>8, LOAD_W0=0, LOAD_W1=1, SHIFT_EN=1)
        assert number(d.WEIGHTS) == value
        await step(d, LOAD_W1=0, SHIFT_EN=0)
        assert number(d.WEIGHTS) == value
        for c in codes:
            assert number(d.WEIGHTS)&3 == c
            await step(d, SHIFT_EN=1)
            value >>= 2
            assert number(d.WEIGHTS) == value
            samples += 1
        await step(d, RST_N=0, LOAD_W0=1, LOAD_W1=1, SHIFT_EN=1, BYTE_DATA=255)
        assert number(d.WEIGHTS) == 0
    elif name == 'nibble_rx':
        await initialize(d, IN=0, IN_VALID=0, IN_READY=1)
        for value in range(256):
            await step(d, IN=value&15, IN_VALID=1, IN_READY=0)
            assert number(d.BYTE_VALID) == 0
            await step(d, IN=value&15, IN_VALID=1, IN_READY=1)
            assert number(d.BYTE_VALID) == 0
            await step(d, IN=15, IN_VALID=0)
            await step(d, IN=value>>4, IN_VALID=1)
            assert number(d.BYTE_DATA) == value and number(d.BYTE_VALID) == 1
            await step(d, IN_VALID=0)
            assert number(d.BYTE_VALID) == 0 and number(d.BYTE_DATA) == value
            samples += 1
        await step(d, IN=9, IN_VALID=1)
        await step(d, RST_N=0)
        await step(d, RST_N=1, IN=3, IN_VALID=1)
        assert number(d.BYTE_VALID) == 0
        await step(d, IN=10)
        assert number(d.BYTE_DATA) == 163 and number(d.BYTE_VALID) == 1
    elif name == 'result_tx':
        await initialize(d, LOAD=0, RESULT_DATA=0)
        for value in (0,65535,1,4095,4096,4660,8191):
            await step(d, LOAD=1, RESULT_DATA=value)
            for i in range(4):
                assert number(d.OUT_VALID) == 1
                assert number(d.OUT) == (value >> (4*i)) & 15
                assert number(d.DONE) == int(i == 3)
                await step(d, LOAD=0)
                samples += 1
            assert number(d.OUT_VALID) == 0 and number(d.DONE) == 0
        await step(d, LOAD=1, RESULT_DATA=1234)
        await step(d, LOAD=1, RESULT_DATA=4321)
        assert number(d.OUT) == 4321&15
        await step(d, RST_N=0, LOAD=1)
        assert number(d.OUT_VALID) == 0
    elif name == 'dot8_controller':
        await initialize(d, BYTE_VALID=0, TX_DONE=0)
        arcs, states = set(), set()
        async def advance(**values):
            before = number(d.state)
            await step(d, **values)
            after = number(d.state)
            states.update((before,after)); arcs.add((before,after))
        async def idle():
            await advance(BYTE_VALID=0, TX_DONE=0)
            assert number(d.IN_READY) == int(number(d.state) != 3)
        await idle()
        for stage in (0,1):
            d.BYTE_VALID.value = 1
            await Timer(1,unit='ns')
            assert number(d.IN_READY) == 0
            assert number(d.LOAD_W0) == int(stage==0)
            assert number(d.LOAD_W1) == int(stage==1)
            assert number(d.WORK_CLEAR) == int(stage==0)
            await advance(BYTE_VALID=1)
            await idle()
        for i in range(8):
            d.BYTE_VALID.value = 1
            await Timer(1,unit='ns')
            assert number(d.ACC_EN) == number(d.WEIGHT_SHIFT) == 1
            assert number(d.RESULT_LOAD) == int(i==7)
            assert number(d.a_index) == i
            await advance(BYTE_VALID=1)
            await idle()
        assert number(d.state) == 3 and number(d.IN_READY) == 0
        await advance(BYTE_VALID=0, TX_DONE=1)
        wanted = {(0,0),(0,1),(1,1),(1,2),(2,2),(2,3),(3,3),(3,0)}
        assert wanted <= arcs, f'missing FSM arcs: {wanted-arcs}'
        assert states == {0,1,2,3}
        await step(d, RST_N=0, BYTE_VALID=1, TX_DONE=1)
        assert number(d.state) == 0 and number(d.a_index) == 0
        extra = {'fsm_states_hit':sorted(states), 'normal_fsm_arcs_hit':sorted(arcs),
                 'normal_fsm_arcs_required':len(wanted)}
        samples = 10
    else:
        raise AssertionError(f'unknown unit DUT: {name}')
    write_stats({'dut':name, 'checks':samples, **extra})
