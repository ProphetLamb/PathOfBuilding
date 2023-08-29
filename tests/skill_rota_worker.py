from dataclasses import dataclass
from multiprocessing import Pool
import plotly.express as px
import math as m
import typing as t
import pandas as pd
from psutil import cpu_count
import copy

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
def to_ticks(time: float) -> int:
    return int(time * 1000)
def to_time(ticks: int) -> float:
  return ticks / 1000

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

def data_to_ticks(data: SkillSetDef):
  data.akt = to_ticks(data.akt)
  data.cdt = to_ticks(data.cdt)
  data.stt = to_ticks(data.stt)
  for skill in data.skills:
    skill.cdt = to_ticks(skill.cdt)

def data_to_time(data: SkillSetDef):
  data.akt = to_time(data.akt)
  data.cdt = to_time(data.cdt)
  data.stt = to_time(data.stt)
  for skill in data.skills:
    skill.cdt = to_time(skill.cdt)

@dataclass
class SimState:
  time: int
  proposed_trigger_skill_index: int
  trigger_next: t.List[int]
  trigger_count: t.List[int]


def quick_sim(data: SkillSetDef) -> t.List[float]:
  data_to_ticks(data)
  state = SimState(data.akt, 0, [skill.cdt for skill in data.skills], [0] * len(data.skills))

  def next_proposed_trigger_skill():
    """ determines the next skill to trigger
    sets state.proposed_trigger_skill_index to the index of the skill to trigger
    increments state.time to the time at which the skill can be triggered
    """
    initial_proposed_trigger_skill_index = state.proposed_trigger_skill_index
    proposed_trigger_skill_index = initial_proposed_trigger_skill_index
    trigger_skill_index = None
    trigger_skill_time = None
    attack_activations = 0
    while trigger_skill_time is None:
      # move to the next skill from the current
      proposed_trigger_skill_index = (proposed_trigger_skill_index + 1) % len(data.skills)
      proposed_trigger_skill_time = state.trigger_next[proposed_trigger_skill_index]
      attack_activations += 1
      # determine the attack on which the global cooldown has expired
      trigger_global_delta = max(data.cdt, attack_activations * data.akt)
      # the trigger can only occur with an attack
      trigger_global_delta = int(ceil(trigger_global_delta, data.akt))
      # add the current server time 
      trigger_global_time = state.time + trigger_global_delta
      # check if the skill can be triggered at the current time
      if proposed_trigger_skill_time > trigger_global_time:
        continue
      # accept the global trigger time as the proposed trigger time
      proposed_trigger_skill_time = trigger_global_time
      # the proposed trigger time is executed with the next server tick
      proposed_trigger_skill_time = int(ceil(proposed_trigger_skill_time, data.stt))
      # update the minimum trigger time
      if trigger_skill_time is not None and proposed_trigger_skill_time >= trigger_skill_time:
        continue
      trigger_skill_index = proposed_trigger_skill_index
      trigger_skill_time = proposed_trigger_skill_time

    state.proposed_trigger_skill_index = trigger_skill_index
    state.time = trigger_skill_time

  def activate_proposed_skill():
    """ activates the proposed skill
    for the skill state.proposed_trigger_skill_index
    sets state.trigger_next of to the skill cooldown
    increments state.trigger_count by one
    """
    # the skill can next trigger at the activation time + its cooldown
    state.trigger_next[state.proposed_trigger_skill_index] = data.skills[state.proposed_trigger_skill_index].cdt
    state.trigger_count[state.proposed_trigger_skill_index] += 1

  activate_proposed_skill()
  while any(cnt <= 1 for cnt in state.trigger_count):
    next_proposed_trigger_skill()
    activate_proposed_skill()

  data_to_time(data)
  return list(to_time(state.time / cnt) for cnt in state.trigger_count)

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
  df = pd.DataFrame(data, index=atk_rates, columns=[skill.uuid for skill in skills])
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

def plot_skills(skills: t.List[Skill], rates: t.List[float], cdr: float = None):
  data = [SkillSetDef(stt = 0.033, akt = 1/i, cdt = (1/cdr) if cdr else 0.15, skills = skills) for i in rates]
  res = []
  with Pool(cpu_count(logical=False)) as p:
    res = list(p.map(exec, data))
  # res = list(map(exec, data))
  calc = [[1/t for t in akt[0]] for akt in res]
  sim = [[1/t for t in akt[1]] for akt in res]
  plot_data(calc, rates, skills, "Calculated")
  plot_data(sim, rates, skills, "Simulated")

def exec(data: SkillSetDef) -> t.Tuple[t.List[float],t.List[float]]:
  for s in data.skills:
    s.reset()
  calc = calculate(copy.deepcopy(data))
  sim = simulate(copy.deepcopy(data))
  return calc, sim
