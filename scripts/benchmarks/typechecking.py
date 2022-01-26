import typing
import datetime
import typeguard
import timeit

repetitions = 100000


def process(n1: int, n2: int):
    n3 = n1


@typeguard.typechecked()
def processT(n1: int, n2: int):
    n3 = n1


t0 = datetime.datetime.now()
for n in range(repetitions):
    process(n, n)
t1 = datetime.datetime.now() - t0

t0 = datetime.datetime.now()
for n in range(repetitions):
    processT(n, n)
t2 = datetime.datetime.now() - t0

print(t1)
print(t2)
