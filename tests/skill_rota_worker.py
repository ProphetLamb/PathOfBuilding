from multiprocessing import Pool
import plotly.express as px
import math as m
import typing as t
import pandas as pd

# utility

class Dyn:
  def __init__(self, **kwargs):
    self.__dict__.update(kwargs)
  def __repr__(self):
    return str(self.__dict__)

class Skill:
  def __init__(self, uuid: str, cd: float):
    self.uuid = uuid
    self.cd = cd
    self.reset()

  def reset(self):
    self.trigger_next = 0
    self.trigger_count = 0

  def __eq__(self, __o: object) -> bool:
    if isinstance(__o, Skill):
      return self.uuid == __o.uuid
    return False

  def __repr__(self) -> str:
    return f"Skill({self.uuid}, {self.cd})"

def ceil(x, base=1):
  return base * m.ceil(x/base)

def floor(x, base=1):
  return base * m.floor(x/base)

def simulate(data: Dyn) -> t.List[float]:
  aps = data.aps
  skills: t.List[Skill] = data.skills
  st = data.st

  time_max = 100
  time_delta = 1 / 10000
  time = 0
  tick = 0
  tick_cur = 0
  trigger_next = 0
  trigger_inc = 1 / aps
  idx = 0
  wasted = 0

  while time < time_max:
    if time >= trigger_next:
      idx_cur = idx
      while skills[idx].trigger_next > time:
        idx = (idx + 1) % len(skills)
        if idx == idx_cur:
          wasted += 1
          trigger_next = time + trigger_inc
          break

      if skills[idx].trigger_next <= time:
        skills[idx].trigger_count += 1
        skills[idx].trigger_next = time + skills[idx].cd
        tick_temp = tick
        while skills[idx].trigger_next > tick_temp:
            tick_temp += (1/st)
        skills[idx].trigger_next = tick_temp
        idx = (idx + 1) % len(skills)
        trigger_next = time + trigger_inc

    time += time_delta

    if tick < time:
      tick_cur = tick
      tick += (1/st)

  rates = [skill.trigger_count / time for skill in skills]
  return rates

def calculate(data: Dyn) -> t.List[float]:
  aps: float = data.aps
  cdt: float = data.cdt
  skills: t.List[Skill] = data.skills
  st: float = data.st

  # for the breaking points we visualize everything as log(x) to log(y).
  # the breaking points are values in attacks per second

  # breaking point, where the trigger time is only constrained by the attack speed
  # the region tt0 is a slope
  tt0_br = 0
  # breaking points, where the cooldown times of some skills are awaited
  tt1_brs = [len(skills) / skill.cd for skill in skills if skill.cd > cdt]
  def skill_tr(s: Skill) -> float:
    # the breaking point, where the trigger time is only constrained by the cooldown time
    # before this its its either tt0 or tt1, depending on the skills
    # after this the trigger time depends on resonance with the attack speed
    tt2_br = len(skills) / ceil(s.cd, 1/st)
    # the breaking point where the the attack speed is so high, that the affect of resonance is negligible
    tt3_br = tt2_br * 8

    # classify in tt region the attack rate is in
    if aps >= tt3_br:
      return 1/ceil(s.cd, 1/st)
    if aps >= tt2_br:
      return -1
    if len(tt1_brs) > 0 and aps >= min(tt1_brs):
      return -1
    if aps >= tt0_br:
      return aps / len(skills)
    return 0

  cds = [skill_tr(skill) for skill in skills]
  if -1 in cds:
    return simulate(data)
  return cds

def exec(data: Dyn) -> t.Tuple[t.List[float],t.List[float]]:
  for s in data.skills:
    s.cd = max(s.cd, data.cdt)
  for s in data.skills:
    s.reset()
  calc = calculate(data)
  sim = simulate(data)
  return sim, calc

def subsample(atk_rates: t.List[float]) -> t.List[float]:
  ss = []
  for i in range(len(atk_rates)):
    ss.append(atk_rates[i])
    if i < len(atk_rates) - 1:
      ss.append((atk_rates[i] + atk_rates[i+1]) / 2)
  return ss

def plot_data(data: t.List[t.List[float]], atk_rates: t.List[float], skills: t.List[Skill], title: str = None):
  df = pd.DataFrame(data, index=atk_rates)
  # rename columns to skill names
  df.columns = [skill.uuid for skill in skills]
  fig = px.line(df)
  fig.update_layout(title=title)
  # label x and y axes
  fig.update_xaxes(title_text="Attack Rate [1/s]")
  fig.update_yaxes(title_text="Trigger Rate [1/s]")
  fig.update_yaxes(type="log")
  # logarithmic x axis values from atk_rates
  fig.update_xaxes(tickvals=atk_rates)
  fig.update_xaxes(type="log")
  fig.show()

def plot_skills(skills: t.List[Skill], atk_rates: t.List[float]):
  data = [Dyn(st = 30, aps = i, cdt = .15, skills = skills) for i in atk_rates]
  res = []
  with Pool(16) as p:
    res = list(p.map(exec, data))
  sim = [r[0] for r in res]
  calc = [r[1] for r in res]
  plot_data(sim, atk_rates, skills, "Simulated")
  plot_data(calc, atk_rates, skills, "Calculated")


