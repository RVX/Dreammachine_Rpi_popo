/*
 * =====================================================================================
 * PROTOCOLO DE ESTIMULACIÓN LUMÍNICA ESTROBOSCÓPICA DINÁMICA (60 MINUTOS)
 * Hardware Target: Microcontrolador RP2350B (Raspberry Pi Pico 2) + MOSFET BUK9M156-100EX
 * Archivo: fls_60min_rp2350b.ino
 * =====================================================================================
 * 
 * FUNDAMENTACIÓN CIENTÍFICA:
 * - Evita la habituación neuronal mediante variaciones rítmicas cortas (2 a 4 min)
 *   en lugar de bloques estáticos largos (Schwartzman et al., 2019; Montgomery et al., 2024).
 * - Frecuencia 10 Hz (Duty Cycle 30%): Sincronización en la corteza visual primaria e
 *   hiperconectividad tálamo-cortical (LGN a V1-V3/hV4/VO1). Genera geometrías de Klüver
 *   y "Joyful Activation" (Amaya et al., 2023; Montgomery et al., 2024).
 * - Frecuencia 3 Hz - 4 Hz (Duty Cycle 50%): Desinhibición cortical (caída de potencia Alpha,
 *   aumento de potencia Theta) e inducción de alucinaciones complejas (CVH) e hipnagogia.
 * - Frecuencias Beta 12 Hz - 18 Hz (Duty Cycle 20-25%): Reactivación y dinamismo perceptivo.
 */

#include <Arduino.h>

// -------------------------------------------------------------------------------------
// CONFIGURACIÓN DE HARDWARE Y CONSTANTES
// -------------------------------------------------------------------------------------
// Pin asignado en la PCB al Gate del MOSFET BUK9M156-100EX (Ajustar según ruteado de la placa)
const uint8_t MOSFET_PIN = 15; 

// Duración total de la sesión: 60 minutos (3,600,000 milisegundos)
const unsigned long TOTAL_SESSION_MS = 3600000UL; 

// Estructura de datos para definir cada micro-fase del protocolo
struct SequenceStep {
  unsigned long durationMs; // Duración del paso en milisegundos
  float startFreq;          // Frecuencia inicial (Hz)
  float endFreq;            // Frecuencia final (Hz)
  float startDuty;          // Ciclo de trabajo inicial (0.0 a 1.0)
  float endDuty;            // Ciclo de trabajo final (0.0 a 1.0)
  bool isOscillating;       // Si es true, aplica una modulación sinusoidal suave
  float oscRateHz;          // Frecuencia de la modulación sinusoidal en Hz
};

// -------------------------------------------------------------------------------------
// TABLA DE SECUENCIAS (16 MICRO-FASES DINÁMICAS - TOTAL 60 MINUTOS)
// -------------------------------------------------------------------------------------
const SequenceStep PROTOCOL[] = {
  // FASE I: Inducción y Sintonización Inicial (00:00 - 08:00 min)
  { 240000UL, 14.0, 10.0, 0.20, 0.30, false, 0.0 }, // Step 0: Rampa de acogida y acondicionamiento (0-4 min)
  { 240000UL, 10.0, 10.0, 0.30, 0.30, false, 0.0 }, // Step 1: Alpha Puro / Geometrías Klüver (4-8 min)

  // FASE II: Alternancia de Estados (08:00 - 24:00 min)
  { 180000UL,  3.5,  3.5, 0.50, 0.50, false, 0.0 }, // Step 2: Inmersión Theta Hipnagógica (8-11 min)
  { 180000UL,  3.5, 12.0, 0.50, 0.30, false, 0.0 }, // Step 3: Sweep ascendente continuo (11-14 min)
  { 240000UL, 10.2, 10.2, 0.30, 0.30, true,  0.1 }, // Step 4: Alpha armónico oscilante +/-0.5Hz (14-18 min)
  { 180000UL,  3.0,  3.0, 0.50, 0.50, false, 0.0 }, // Step 5: Theta profundo / Visiones CVH (18-21 min)
  { 180000UL, 15.0, 15.0, 0.25, 0.25, false, 0.0 }, // Step 6: Estimulación Beta / Anti-habituación (21-24 min)

  // FASE III: Variación Rítmica y Modulación Dinámica (24:00 - 48:00 min)
  { 240000UL, 10.0, 10.0, 0.30, 0.30, true,  0.25}, // Step 7: Alternancia rítmica rápida (24-28 min)
  { 240000UL,  9.0,  9.0, 0.35, 0.35, true,  0.05}, // Step 8: Sweep senoidal Alpha/Theta flotante (28-32 min)
  { 240000UL,  3.2,  3.2, 0.50, 0.50, false, 0.0 }, // Step 9: Inmersión Hipnagógica secundaria (32-36 min)
  { 240000UL, 10.0, 10.0, 0.20, 0.40, false, 0.0 }, // Step 10: Alpha brillante con barrido de Duty Cycle (36-40 min)
  { 240000UL, 16.0, 18.0, 0.20, 0.25, false, 0.0 }, // Step 11: Rampa a Beta Alta (40-44 min)
  { 240000UL,  9.5,  9.5, 0.30, 0.30, false, 0.0 }, // Step 12: Regreso a Alpha relajante (44-48 min)

  // FASE IV: Cooldown, Consolidador y Apagado (48:00 - 60:00 min)
  { 240000UL,  8.0,  6.0, 0.35, 0.35, false, 0.0 }, // Step 13: Transición intermedia (48-52 min)
  { 240000UL,  5.0,  2.0, 0.35, 0.20, false, 0.0 }, // Step 14: Descenso paulatino (52-56 min)
  { 240000UL,  2.0,  0.2, 0.20, 0.00, false, 0.0 }  // Step 15: Apagado y retorno a estado basal (56-60 min)
};

const size_t NUM_STEPS = sizeof(PROTOCOL) / sizeof(PROTOCOL[0]);

// -------------------------------------------------------------------------------------
// VARIABLES GLOBALES DE ESTADO
// -------------------------------------------------------------------------------------
unsigned long sessionStartMs = 0;   // Timestamp de inicio de la sesión
unsigned long previousMicros = 0;   // Temporizador no bloqueante para conmutación PWM
bool ledState = false;              // Estado actual de la salida del MOSFET (HIGH/LOW)
bool sessionFinished = false;       // Bandera de finalización de la sesión de 60 minutos

// Prototipo de función
void updateCurrentParameters(unsigned long elapsedMs, float &outFreq, float &outDuty);

// -------------------------------------------------------------------------------------
// CONFIGURACIÓN INICIAL (SETUP)
// -------------------------------------------------------------------------------------
void setup() {
  // Configurar el pin del MOSFET como salida digital
  pinMode(MOSFET_PIN, OUTPUT);
  digitalWrite(MOSFET_PIN, LOW); // Garantizar apagado inicial
  
  // Guardar el tiempo de inicio de la sesión
  sessionStartMs = millis();
}

// -------------------------------------------------------------------------------------
// BUCLE PRINCIPAL (LOOP)
// -------------------------------------------------------------------------------------
void loop() {
  // Si la sesión ya concluyó, mantener los LEDs apagados y salir
  if (sessionFinished) {
    digitalWrite(MOSFET_PIN, LOW);
    return;
  }

  unsigned long currentMs = millis();
  unsigned long elapsedMs = currentMs - sessionStartMs;

  // 1. Control del límite total de tiempo (60 minutos)
  if (elapsedMs >= TOTAL_SESSION_MS) {
    digitalWrite(MOSFET_PIN, LOW);
    sessionFinished = true;
    return;
  }

  // 2. Calcular la frecuencia y el duty cycle actuales basados en la fase del protocolo
  float currentFreq = 10.0;
  float currentDuty = 0.30;
  updateCurrentParameters(elapsedMs, currentFreq, currentDuty);

  // 3. Generación de onda cuadrada mediante temporización precisa en microsegundos
  unsigned long currentMicros = micros();
  
  // Cálculo de los periodos de tiempo en encendido (ON) y apagado (OFF)
  unsigned long totalPeriodMicros = (unsigned long)(1000000.0 / currentFreq);
  unsigned long onTimeMicros = (unsigned long)(totalPeriodMicros * currentDuty);
  unsigned long offTimeMicros = totalPeriodMicros - onTimeMicros;

  // Determinar el intervalo objetivo según el estado del LED
  unsigned long targetInterval = ledState ? onTimeMicros : offTimeMicros;

  // Conmutación del MOSFET cuando transcurre el intervalo correspondiente
  if (currentMicros - previousMicros >= targetInterval) {
    previousMicros = currentMicros;
    ledState = !ledState;
    digitalWrite(MOSFET_PIN, ledState ? HIGH : LOW);
  }
}

// -------------------------------------------------------------------------------------
// FUNCIÓN DE CÁLCULO CONTINUO DE PARÁMETROS
// -------------------------------------------------------------------------------------
/**
 * Determina en qué micro-fase se encuentra la sesión y calcula la interpolación lineal
 * o modulación sinusoidal de la frecuencia y del ciclo de trabajo en tiempo real.
 */
void updateCurrentParameters(unsigned long elapsedMs, float &outFreq, float &outDuty) {
  unsigned long accumulatedMs = 0;

  for (size_t i = 0; i < NUM_STEPS; i++) {
    unsigned long stepDuration = PROTOCOL[i].durationMs;

    // Verificar si el tiempo transcurrido cae dentro del rango de este paso
    if (elapsedMs < accumulatedMs + stepDuration) {
      unsigned long timeInStep = elapsedMs - accumulatedMs;
      float progress = (float)timeInStep / (float)stepDuration; // Progreso normalizado de 0.0 a 1.0

      // Interpolación lineal básica de frecuencia y duty cycle
      outFreq = PROTOCOL[i].startFreq + (PROTOCOL[i].endFreq - PROTOCOL[i].startFreq) * progress;
      outDuty = PROTOCOL[i].startDuty + (PROTOCOL[i].endDuty - PROTOCOL[i].startDuty) * progress;

      // Si el paso requiere oscilación, añadir modulación sinusoidal
      if (PROTOCOL[i].isOscillating) {
        float timeSec = (float)timeInStep / 1000.0;
        outFreq += 0.5 * sin(2.0 * PI * PROTOCOL[i].oscRateHz * timeSec);
      }
      return;
    }
    accumulatedMs += stepDuration;
  }

  // Si se supera el límite de la tabla, mantener en apagado
  outFreq = 0.5;
  outDuty = 0.0;
}
