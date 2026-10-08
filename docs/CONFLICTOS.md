# Conflictos y prioridades — F7777techMods

## Qué es un conflicto

Dos o más mods del plan escriben el mismo archivo relativo en el destino.

## Resolución

1. Prioridades por mod (orden).
2. Resoluciones explícitas por archivo cuando existen.
3. Simulación muestra el ganador efectivo antes de Apply.

## Semántica FF7R

Heurística por nombres de archivo (slots de personaje, etc.). No analiza el interior del `.pak`.

## Protección

Archivos EXTERNOS / DESCONOCIDOS / VORTEX no se sobrescriben ni borran sin adopción explícita.
