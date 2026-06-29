"""Módulo de estados do bot"""
from telebot.handler_backends import State, StatesGroup

class UserStates(StatesGroup):
    waiting_phone = State()
    waiting_pin = State()
    waiting_operator = State()  # Novo estado para aguardar seleção da operadora