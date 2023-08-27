from multiprocessing import Pool
import plotly.express as px
import math as m
import typing as t
import pandas as pd
from psutil import cpu_count

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
  aps: float = data.aps # attacks per second
  att: float = 1/aps # attack time
  skills: t.List[Skill] = data.skills
  stf: float = data.st # server tick frequency
  stt: float = 1/stf # server tick time
  cdt: float = data.cdt # cooldown time

  class Activation:
    """ Represents an activation of a skill. """
    def __init__(self, skill: Skill):
      self.skill = skill
      self.delta_time = 0.0
      self.time = 0.0
      self.count = 0

    def __eq__(self, __o: object) -> bool:
      if isinstance(__o, Activation):
        return self.skill == __o.skill and self.delta_time == __o.delta_time
      return False

    def get_avg_rate(self) -> float:
      """ returns the average frequency of activations """
      return self.count / self.time

    def time_ready(self) -> float:
      """ returns the time when the skill is ready """
      return self.time + self.skill.cd

    def activate(self, time: float):
      """ activate the skill at the given time, update the activation """
      self.delta_time = time - self.time
      self.time = time
      self.count += 1

  class State:
    """ Iterator representing the state of a triggered skill rotation. """
    def __init__(self, skills: t.List[Skill]):
      self.activations = [Activation(skill) for skill in skills]
      self.time = 0.0
      self.current_activation = 0

    def iter(self) -> t.Iterator[Activation]:
      """ iterate over all activations in order """
      idx = self.current_activation
      count = len(self.activations)
      for _ in range(count):
        yield self.activations[idx]
        idx = (idx + 1) % count

    def iter_time_ready(self) -> t.Iterator[t.Tuple[float, Activation]]:
      """ iterate over all activations and the time at which each skill is ready """
      # the time at which the next attack will be ready
      time_penalty = self.time + att
      for activation in self.iter():
        # the time until the skill is ready
        time_ready = activation.time_ready()
        # wait for the next attack
        time_ready = ceil(time_ready, att)
        # wait until the attack rotation is ready
        time_ready = max(time_ready, time_penalty)
        yield time_ready, activation

    def get_nearest_ready(self) -> t.Tuple[float, Activation]:
      """ Returns the next activation and the time until the skill is ready."""
      nearest_time = 0.0
      nearest_activation = None
      for time_ready,activation in self.iter_time_ready():
        if nearest_activation is None or time_ready < nearest_time:
          nearest_time = time_ready
          nearest_activation = activation
      return nearest_time, nearest_activation

    def activate(self) -> Activation:
      """ Activates the activation nearest to ready."""
      time, activation = self.get_nearest_ready()
      # round up time to the next server tick
      time = ceil(time, stt)
      activation.activate(time)
      self.time = time
      self.current_activation = self.activations.index(activation)
      return activation

    def skip(self):
      """ Skips one skill in the rotation. """
      self.current_activation = (self.current_activation + 1) % len(self.activations)

    def move_next_round(self):
      """ Move to the next round of activations."""
      initial_activation = self.current_activation
      is_initial = True
      # next until a full round has been completed
      while self.activate() is not None and (is_initial or self.current_activation != initial_activation):
        self.skip()
        is_initial = False

    def get_avg_rates(self) -> t.Iterator[float]:
      """ Returns the average cooldown in rates for each skill."""
      for activation in self.activations:
        yield activation.get_avg_rate()

    def limit_simulation(self, count: float):
      """ Simulate the rotation until the limit is exceeded but ensure that all skills are triggered at least once."""
      while count > 0 or any(activation.count == 0 for activation in self.iter()):
        self.move_next_round()
        count -= 1

  rates = [0.0] * len(skills)
  for i in range(len(skills)):
    state = State(skills)
    state.current_activation = i
    # initial rotation
    state.move_next_round()
    # simulate rotations until the limit is exceeded
    state.limit_simulation(16)
    rates = [r + a for r,a in zip(rates, state.get_avg_rates())]

  return [r / len(skills) for r in rates]

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
    return quick_sim(data)
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

def plot_skills(skills: t.List[Skill], atk_rates: t.List[float], cdt: float = None):
  data = [Dyn(st = 30, aps = i, cdt = cdt if cdt else 0.15, skills = skills) for i in atk_rates]
  res = []
  with Pool(cpu_count(logical=False)) as p:
    res = list(p.map(exec, data))
  # res = list(map(exec, data))
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
