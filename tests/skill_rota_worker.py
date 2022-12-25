from multiprocessing import Pool
import plotly.express as px
import math as m
import typing as t
import pandas as pd
from copy import deepcopy

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

def round_up_div(x,y) -> int:
  """ Round up integer division."""
  return m.ceil(x/y)

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
      tick += (1/st)

  rates = [skill.trigger_count / time for skill in skills]
  return rates

def quick_sim(data: Dyn) -> t.List[float]:
  aps: float = data.aps
  skills: t.List[Skill] = data.skills
  stt: float = 1/data.st

  class Activation:
    def __init__(self, skill: Skill):
      self.skill = skill
      self.tick = 0
      self.count = 0

    def __eq__(self, __o: object) -> bool:
      if isinstance(__o, Activation):
        return self.skill == __o.skill and self.tick == __o.tick
      return False

    def ticks_ready(self) -> int:
      """ returns the time when the skill is ready """
      return self.tick + round_up_div(self.skill.cd, stt)

    def activate(self, tick: int):
      """ activate the skill at the given tick """
      self.tick = tick
      self.count += 1

  class State:
    def __init__(self, skills: t.List[Skill]):
      self.activations = [Activation(skill) for skill in skills]
      self.tick = 0
      self.current_activation = 0

    def iter(self) -> t.Iterator[Activation]:
      """ iterate over all activations in order """
      idx = self.current_activation
      count = len(self.activations)
      for _ in range(count):
        idx = (idx + 1) % count
        yield self.activations[idx]

    def iter_with_ticks(self) -> t.Iterator[t.Tuple[int, Activation]]:
      for activation in self.iter():
        # the ticks until the skill is ready
        ticks_ready = activation.ticks_ready()
        # wait for the next attack tick
        ticks_ready = round_up_div(ceil(ticks_ready*stt, aps), stt)
        yield ticks_ready, activation

    def get_next(self) -> t.Tuple[int, Activation]:
      """ Returns the next activation and the ticks when the skill is ready."""
      nearest: t.Tuple[int, Activation] = None
      for ticks,activation in self.iter_with_ticks():
        if nearest is None or ticks < nearest[0]:
          nearest = (ticks, activation)
      return nearest

    def move_next(self) -> Activation:
      """ Move to the next activation, returns the activation."""
      tick, activation = self.get_next()
      activation.activate(tick)
      self.tick = tick + 1 # tick beyond the activation
      self.current_activation = self.activations.index(activation)
      return activation

    def move_next_round(self):
      """ Move to the next round of activations."""
      initial_activation = self.current_activation
      while self.move_next():
        if self.current_activation == initial_activation:
          # a full round has been completed
          break

    def avg_cd_ticks(self) -> t.Iterator[float]:
      """ Returns the average cooldown in ticks for each skill."""
      for activation in self.iter():
        yield activation.count / self.tick

  state = State(skills)
  # initial rotation
  state.move_next_round()
  initial_rot = [deepcopy(s) for s in state.iter()]
  # limit rotations in simulation
  sim_rot_max = 40
  sim_rot = 0
  def rot_eq(rot1, rot2):
    """ determines whether two rotations are equal """
    for s1,s2 in zip(rot1, rot2):
      if s1 != s2:
        return False
    return True

  # simulate rotations until the initial rotation is reached again or the limit is exceeded
  while sim_rot < sim_rot_max:
    sim_rot += 1
    state.move_next_round()
    if rot_eq(initial_rot, state.iter()):
      break

  return [stt/t for t in state.avg_cd_ticks()]

def calculate(data: Dyn) -> t.List[float]:
  aps: float = data.aps
  cdt: float = data.cdt
  skills: t.List[Skill] = data.skills
  stf: float = 1/data.st

  # for the breaking points we visualize everything as log(x) to log(y).
  # the breaking points are values in attacks per second

  # breaking point, where the trigger time is only constrained by the attack speed
  # the region tt0 is a slope
  tt0_br = 0
  # breaking points, where the cooldown times of some skills are awaited
  tt1_brs = [len(skills) / ceil(s.cd,stf) for s in skills if s.cd > cdt]
  def skill_tr(s: Skill) -> float:
    # the breaking point, where the trigger time is only constrained by the cooldown time
    # before this its its either tt0 or tt1, depending on the skills
    # after this the trigger time depends on resonance with the attack speed
    tt2_br = len(skills) / ceil(s.cd,stf) * .8
    # the breaking point where the the attack speed is so high, that the affect of resonance is negligible
    tt3_br = len(skills) / floor(s.cd,stf) * 8


    # classify in tt region the attack rate is in
    if aps >= tt3_br:
      return 1/ceil(s.cd,stf)
    if aps >= tt2_br:
      return -1
    if len(tt1_brs) > 0 and aps >= min(tt1_brs):
      return -1
    if aps >= tt0_br:
      return aps / len(skills)
    return 0

  cds = [skill_tr(skill) for skill in skills]

  if -1 in cds:
    return [0 for _ in skills ] # quick_sim(data)
  return cds

def subsample(atk_rates: t.List[float], depth: int = 1) -> t.List[float]:
  if depth <= 0:
    return atk_rates
  atk_rates = subsample(atk_rates, depth - 1)
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

def exec(data: Dyn) -> t.Tuple[t.List[float],t.List[float]]:
  for s in data.skills:
    s.cd = max(s.cd, data.cdt)
  for s in data.skills:
    s.reset()
  calc = calculate(data)
  sim = simulate(data)
  return sim, calc
