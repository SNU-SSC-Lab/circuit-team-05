import json
import os
from pathlib import Path

from cocotb.triggers import Timer
from model import decode, expected, packet


async def step(dut, **values):
    dut.CLK.value = 0
    for name, value in values.items():
        getattr(dut, name).value = value
    await Timer(50, unit='ns')
    dut.CLK.value = 1
    await Timer(50, unit='ns')


def number(handle):
    assert handle.value.is_resolvable, f'unknown valid signal: {handle._name}={handle.value}'
    return int(handle.value)


def write_stats(values):
    path = os.environ.get('SSC_STATS')
    if path:
        Path(path).write_text(json.dumps(values, ensure_ascii=False, indent=2), encoding='utf-8')


class TopIO:
    def __init__(self, dut):
        self.dut, self.cycle, self.outputs = dut, 0, []
        self.jobs, self.max_latency, self.wait_cycles = 0, 0, 0

    async def tick(self, valid=0, data=0, rst=1):
        d = self.dut
        # Inputs change at the falling edge. Sample the stable values BEFORE rising.
        d.CLK.value = 0
        d.RST_N.value = rst
        d.IN_VALID.value = valid
        d.IN.value = data
        await Timer(50, unit='ns')
        ready = number(d.IN_READY) if rst else 0
        if rst and number(d.OUT_VALID):
            self.outputs.append((self.cycle+1, number(d.OUT)))
        d.CLK.value = 1
        await Timer(50, unit='ns')
        self.cycle += 1
        return ready

    async def reset(self):
        for _ in range(4):
            await self.tick(rst=0)
        self.outputs.clear()
        for _ in range(2):
            await self.tick(rst=1)

    async def send(self, nibble):
        for _ in range(256):
            if await self.tick(valid=1, data=nibble):
                return self.cycle
            self.wait_cycles += 1
        raise AssertionError('input acceptance timed out')

    def verify(self, codes, inputs, last_edge):
        assert len(self.outputs) == 4, f'output count={len(self.outputs)}'
        latency = self.outputs[0][0] - last_edge
        assert 0 < latency <= 32, f'response latency={latency}'
        actual = decode([n for _, n in self.outputs])
        wanted = expected(codes, inputs)
        assert actual == wanted, f'weights={codes}, input={inputs}, wanted={wanted}, got={actual}'
        assert actual >> 13 == 0, 'reserved result bits must be zero'
        assert [c for c, _ in self.outputs] == list(range(self.outputs[0][0], self.outputs[0][0]+4)), 'nonconsecutive output'
        self.max_latency = max(self.max_latency, latency)
        self.jobs += 1
        self.outputs.clear()

    async def finish(self, codes, inputs, last_edge, idle=True):
        for _ in range(36):
            if len(self.outputs) >= 4:
                break
            await self.tick()
        self.verify(codes, inputs, last_edge)
        if idle:
            await self.tick()
            assert not self.outputs, 'extra result nibble'

    async def transact(self, codes, inputs, rng=None):
        assert not self.outputs, 'unconsumed output before a new job'
        for nibble in packet(codes, inputs):
            if rng is not None and rng.randrange(4) == 0:
                for _ in range(rng.randrange(1, 4)):
                    await self.tick(data=rng.randrange(16))
            last = await self.send(nibble)
        await self.finish(codes, inputs, last)

    def stats(self, scenario):
        return {'scenario': scenario, 'jobs': self.jobs, 'cycles': self.cycle,
                'max_response_cycles': self.max_latency, 'ready_wait_cycles': self.wait_cycles}
