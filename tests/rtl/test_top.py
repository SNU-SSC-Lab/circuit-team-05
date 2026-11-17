import itertools
import json
import os
import random
from pathlib import Path
import cocotb
from model import packet
from transport import TopIO, number, write_stats

CONFIG = json.loads(Path(os.environ['SSC_DESIGN']).read_text(encoding='utf-8'))


@cocotb.test()
async def boundary_packets(d):
    io = TopIO(d); await io.reset()
    vectors = [([1,0,2,1,2,0,1,2],[10,-20,30,40,-50,60,70,-80]),
               ([2]*8,[-128]*8),([1]*8,[-128]*8),([1]*8,[127]*8),
               ([0]*8,[-128,127,-1,0,1,2,3,4]),([1]+[0]*7,[-1]+[0]*7),
               ([1]*8,[127,-127]*4)]
    for codes,inputs in vectors:
        await io.transact(codes,inputs)
    write_stats(io.stats('I01'))


@cocotb.test()
async def positions_and_illegal(d):
    io = TopIO(d); await io.reset()
    inputs = [-128,-17,-1,0,1,9,127,31]
    for i in range(8):
        for code in (1,2):
            codes=[0]*8; codes[i]=code
            await io.transact(codes,inputs)
    for positions in [[i] for i in range(8)]+[[0,7],[2,3,4],list(range(8))]:
        codes=[1]*8
        for i in positions: codes[i]=3
        await io.transact(codes,inputs)
        await io.transact([0]*8,[0]*8)  # Error and sum clear without a global reset.
    write_stats(io.stats('I02'))


@cocotb.test()
async def protocol_and_back_to_back(d):
    io = TopIO(d); await io.reset()
    rng=random.Random(CONFIG['seed'])
    for _ in range(30):
        await io.tick(valid=0,data=rng.randrange(16))
        assert not io.outputs
    for _ in range(30):
        await io.transact([rng.randrange(4) for _ in range(8)],
                          [rng.randrange(-128,128) for _ in range(8)],rng)
    first=([2]*8,[-128]*8); second=([1]*8,[1]*8)
    for nibble in packet(*first): last=await io.send(nibble)
    # Offer next W0 while prior result is in flight; hold until READY accepts it.
    next_packet=packet(*second)
    await io.send(next_packet[0])
    io.verify(*first,last)
    for nibble in next_packet[1:]: second_last=await io.send(nibble)
    await io.finish(*second,second_last)
    assert io.wait_cycles > 0
    write_stats(io.stats('I03'))


@cocotb.test()
async def reset_each_phase(d):
    io=TopIO(d)
    old=([3,2,1,0,1,2,3,1],[-128,127,-1,4,5,-6,7,8])
    recovery=([1]*8,[1,2,3,4,5,6,7,8])
    for count in range(21):
        await io.reset()
        for nibble in packet(*old)[:count]: await io.send(nibble)
        await io.reset()
        await io.transact(*recovery)
    for output_index in range(4):
        await io.reset()
        for nibble in packet(*old): await io.send(nibble)
        for _ in range(32):
            if number(d.OUT_VALID): break
            await io.tick()
        assert number(d.OUT_VALID)
        for _ in range(output_index): await io.tick()
        await io.reset()
        await io.transact(*recovery)
    write_stats(io.stats('I04'))


@cocotb.test()
async def all_legal_weights(d):
    io=TopIO(d); await io.reset()
    for codes in itertools.product(range(3),repeat=8):
        for inputs in CONFIG['boundary_patterns']:
            await io.transact(codes,inputs)
        if io.jobs % 10000 == 0: d._log.info('legal regression: %d jobs',io.jobs)
    assert io.jobs == 3**8 * len(CONFIG['boundary_patterns'])
    write_stats(io.stats('R01'))


@cocotb.test()
async def random_jobs(d):
    io=TopIO(d); await io.reset()
    rng=random.Random(CONFIG['seed'])
    for _ in range(CONFIG['random_jobs']):
        await io.transact([rng.randrange(4) for _ in range(8)],
                          [rng.randrange(-128,128) for _ in range(8)],rng)
    assert io.jobs == CONFIG['random_jobs']
    write_stats(io.stats('R02'))
