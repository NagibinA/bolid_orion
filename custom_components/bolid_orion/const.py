"""Константы для интеграции Bolid Orion v2.0.0"""

DOMAIN = "bolid_orion"
VERSION = "2.0.0"

# MQTT топики
TOPIC_COMMAND = "WemosOrion/byteN"
TOPIC_ANSWER = "WemosOrion/answer"

# Типы ответов
RSP_ORION = 0
RSP_DPLS = 58
RSP_STATUS = 26
RSP_ADC = 28

# Типы Orion устройств
ORION_DEVICE_TYPES = {
    1: "Сигнал-20",
    2: "Сигнал-20П",
    3: "Сигнал-20М",
    9: "С2000-КДЛ",
    44: "С2000-БКИ",
    7: "С2000-К",
    10: "С2000-БИ",
}

# Типы DPLS устройств
DPLS_DEVICE_TYPES = {
    90: "С2000-ИК исп.03",
    3: "АР1 исп.02",
    64: "ИПР 513-3АМ",
    207: "С2000-СП2",
}