from dataclasses import dataclass
from multiprocessing import Pool
import plotly.express as px
import math as m
import typing as t
import pandas as pd
from psutil import cpu_count

# utility

@dataclass
class Skill:
  """ Represents a skill in a skill rotation.
    @param uuid: the unique id of the skill
    @param cd: the cooldown time in seconds
    @param trigger_next: the time of the next trigger
    @param trigger_count: the number of times the skill has been triggered
  """
  uuid: str
  """ The unique id of the skill."""
  cdt: float
  """ The cooldown time in seconds."""
  trigger_next: float = 0
  """ The time of the next trigger."""
  trigger_count: int = 0
  """ The number of times the skill has been triggered."""

  def reset(self):
    self.trigger_next = 0
    self.trigger_count = 0

  def __eq__(self, __o: object) -> bool:
    if isinstance(__o, Skill):
      return self.uuid == __o.uuid
    return False

@dataclass
class SkillSetDef:
  """ Represents a skill set definition.
    @param stt: The server tick time in seconds.
    @param akt: The attack time in seconds.
    @param cdt: The cooldown time in seconds
    @param skills: The skills in the rotation
  """
  stt: float
  """ The server tick time in seconds."""
  akt: float
  """ The attack time in seconds."""
  cdt: float
  """ The cooldown time in seconds."""
  skills: t.List[Skill]
  """ The skills in the rotation."""
                 
def ceil(x, base=1):
  return base * m.ceil(x/base)

def round_up_div(x,y) -> int:
  """ Round up integer division."""
  return m.ceil(x/y)

def floor(x, base=1):
  return base * m.floor(x/base)

def simulate(data: SkillSetDef) -> t.List[float]:
  time_max = 100
  time_delta = 1 / 10000
  time = 0
  tick = 0
  trigger_next = 0
  trigger_inc = data.akt
  idx = 0
  wasted = 0

  while time < time_max:
    if time >= trigger_next:
      idx_cur = idx
      while data.skills[idx].trigger_next > time:
        idx = (idx + 1) % len(data.skills)
        if idx == idx_cur: 
          wasted += 1
          trigger_next = time + trigger_inc
          break

      if data.skills[idx].trigger_next <= time:
        data.skills[idx].trigger_count += 1
        data.skills[idx].trigger_next = time + data.skills[idx].cdt
        tick_temp = tick
        while data.skills[idx].trigger_next > tick_temp:
            tick_temp += data.stt
        data.skills[idx].trigger_next = tick_temp
        idx = (idx + 1) % len(data.skills)
        trigger_next = time + trigger_inc

    time += time_delta

    if tick < time:
      tick += data.stt

  times = [time / skill.trigger_count for skill in data.skills]
  return times

def quick_sim(data: SkillSetDef) -> t.List[float]:
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

    def get_avg_time(self) -> float:
      """ returns the average time between activations """
      return self.time / self.count

    def time_ready(self) -> float:
      """ returns the time when the skill is ready """
      return self.time + self.skill.cdt

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
      time_penalty = self.time + data.akt
      for activation in self.iter():
        # the time until the skill is ready
        time_ready = activation.time_ready()
        # wait for the next attack
        time_ready = ceil(time_ready, data.akt)
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
      time = ceil(time, data.stt)
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

    def get_avg_time(self) -> t.Iterator[float]:
      """ Returns the average cooldown time for each skill."""
      for activation in self.activations:
        yield activation.get_avg_time()

    def limit_simulation(self, count: float):
      """ Simulate the rotation until the limit is exceeded but ensure that all skills are triggered at least once."""
      while count > 0 or any(activation.count == 0 for activation in self.iter()):
        self.move_next_round()
        count -= 1

  times = [0.0] * len(data.skills)
  for i in range(len(data.skills)):
    state = State(data.skills)
    state.current_activation = i
    # initial rotation
    state.move_next_round()
    # simulate rotations until the limit is exceeded
    state.limit_simulation(2)
    times = [time + avg for time,avg in zip(times, state.get_avg_time())]

  return [t / len(data.skills) for t in times]

def calculate(data: SkillSetDef) -> t.List[float]:
  # for the breaking points we visualize everything as log(x) to log(y).
  # the breaking points are values in attacks per second

  return quick_sim(data)

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

def plot_skills(skills: t.List[Skill], rates: t.List[float], cdt: float = None):
  data = [SkillSetDef(stt = 0.033, akt = 1/i, cdt = cdt if cdt else 0.15, skills = skills) for i in rates]
  res = []
  # with Pool(cpu_count(logical=False)) as p:
  #   res = list(p.map(exec, data))
  res = list(map(exec, data))
  calc = [1/t for akt in res for t in akt[1]]
  sim = [1/t for akt in res for t in akt[0]]
  plot_data(calc, rates, skills, "Calculated")
  plot_data(sim, rates, skills, "Simulated")

def exec(data: SkillSetDef) -> t.Tuple[t.List[float],t.List[float]]:
  for s in data.skills:
    s.reset()
  calc = calculate(data)
  sim = simulate(data)
  return calc, sim
