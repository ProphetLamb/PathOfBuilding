
import time
from skill_rota_worker import *
from psutil import cpu_count
import numpy as np
import datetime
from prettytable import PrettyTable

def exec(data: Dyn) -> t.Tuple[t.List[float],t.List[float]]:
  for s in data.skills:
    s.cd = max(s.cd, data.cdt)
  for s in data.skills:
    s.reset()
  start_ts = time.thread_time_ns()
  calc = calculate(data)
  calc_dt = (time.thread_time_ns() - start_ts) / 1e6
  start_ts = time.thread_time_ns()
  sim = simulate(data)
  sim_dt = (time.thread_time_ns() - start_ts) / 1e6
  return sim, sim_dt, calc, calc_dt

def bm_skills(skills: t.List[Skill], atk_rates: t.List[float]):
  data = [Dyn(st = 30, aps = i, cdt = .15, skills = skills) for i in atk_rates]
  res = []
  with Pool(cpu_count(logical=False)) as p:
    res = list(p.map(exec, data))
  # res = list(map(exec, data))
  sim = [r[0] for r in res]
  sim_dt = [r[1] for r in res]
  calc = [r[2] for r in res]
  calc_dt = [r[3] for r in res]
  return sim, sim_dt, calc, calc_dt

def print_stats(sim_t: t.List[float], calc_t: t.List[float]):
  # evaluate mean of results
  sim_mean = np.mean(sim_t)
  calc_mean = np.mean(calc_t)
  # evaluate median of results
  sim_median = np.median(sim_t)
  calc_median = np.median(calc_t)
  # evaluate 25th and 75th percentile of results
  sim_25 = np.percentile(sim_t, 25)
  sim_75 = np.percentile(sim_t, 75)
  calc_25 = np.percentile(calc_t, 25)
  calc_75 = np.percentile(calc_t, 75)
  # evaluate min and max of results
  sim_min = np.min(sim_t)
  sim_max = np.max(sim_t)
  calc_min = np.min(calc_t)
  calc_max = np.max(calc_t)
  # evaluate standard deviation of results
  sim_std = np.std(sim_t)
  calc_std = np.std(calc_t)

  # print results to the console
  tbl = PrettyTable()
  tbl.add_column('Metric', ['Mean [ms]', 'Median [ms]', '25th [ms]', '75th [ms]', 'Min [ms]', 'Max [ms]', 'Std [ms]'])
  tbl.add_column('Simulate', [sim_mean, sim_median, sim_25, sim_75, sim_min, sim_max, sim_std])
  tbl.add_column('Calculate', [calc_mean, calc_median, calc_25, calc_75, calc_min, calc_max, calc_std])
  print(tbl)


def get_time_str():
  return datetime.datetime.now().strftime("%X")

def main():
  skill_sets = [
    [Skill('Ice Spear', 0)],
    [Skill('Ice Spear', 0), Skill('Arc', 0)],
    [Skill('Frost Bomb', 2.5), Skill('Arc', 0)],
    [Skill('Ice Spear', 0), Skill('Frost Bomb', 2.5)],
    [Skill('Frost Bomb', 2.5), Skill('Arc', 0), Skill('Ice Spear', 0)],
  ]
  atk_rates = subsample([4, 8, 16, 32, 64], depth=6)
  for skills in  skill_sets:
    print(f"{get_time_str()}: begin {' '.join([s.uuid for s in skills])}")
    sim, sim_dt, calc, calc_dt = bm_skills(skills, atk_rates)
    print(f"{get_time_str()}: finish {' '.join([s.uuid for s in skills])}")
    print_stats(sim_dt, calc_dt)

if __name__ == '__main__':
  main()
