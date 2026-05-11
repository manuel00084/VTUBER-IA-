import time
import random
import numpy as np

class SimpleAI:
    """IA simple que aprende a jugar"""
    
    def __init__(self):
        self.q_table = {}
        self.learning_rate = 0.1
        self.discount = 0.9
        self.epsilon = 0.3
    
    def get_q(self, state, action):
        key = (tuple(state), action) if isinstance(state, (list, tuple)) else (state, action)
        return self.q_table.get(key, 0.0)
    
    def set_q(self, state, action, value):
        key = (tuple(state), action) if isinstance(state, (list, tuple)) else (state, action)
        self.q_table[key] = value
    
    def choose_action(self, state, actions):
        """Elegir acción con epsilon-greedy"""
        if random.random() < self.epsilon:
            return random.choice(actions)
        
        q_values = [self.get_q(state, a) for a in actions]
        max_q = max(q_values)
        if q_values.count(max_q) > 1:
            return random.choice([a for a, q in zip(actions, q_values) if q == max_q])
        return actions[q_values.index(max_q)]
    
    def learn(self, state, action, reward, next_state=None, actions=None):
        """Aprender de la acción"""
        old_q = self.get_q(state, action)
        
        if next_state and actions:
            max_next_q = max([self.get_q(next_state, a) for a in actions])
            new_q = old_q + self.learning_rate * (reward + self.discount * max_next_q - old_q)
        else:
            new_q = old_q + self.learning_rate * (reward - old_q)
        
        self.set_q(state, action, new_q)
    
    def reset(self):
        """Reiniciar aprendizaje"""
        self.q_table = {}


class RuleBasedAI:
    """IA basada en reglas simples"""
    
    def __init__(self):
        self.actions = []
        self.last_state = None
        self.score = 0
    
    def add_action(self, name, func):
        """Agregar acción"""
        self.actions.append((name, func))
    
    def update(self, screen_data):
        """Actualizar según pantalla"""
        return None
    
    def execute(self, action_idx):
        """Ejecutar acción"""
        if 0 <= action_idx < len(self.actions):
            self.actions[action_idx][1]()


class AutoPlayer:
    """Jugador automático"""
    
    def __init__(self):
        self.state = "idle"
        self.screen_region = None
        self.click_interval = 0.5
        self.running = False
    
    def start(self):
        """Iniciar"""
        self.running = True
        self.state = "playing"
    
    def stop(self):
        """Parar"""
        self.running = False
        self.state = "idle"
    
    def set_region(self, region):
        """Definir región de pantalla"""
        self.screen_region = region
    
    def set_interval(self, interval):
        """Intervalo entre clicks"""
        self.click_interval = interval


auto_player = AutoPlayer()
simple_ai = SimpleAI()
rule_ai = RuleBasedAI()