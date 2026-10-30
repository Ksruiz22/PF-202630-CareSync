/**
 * El progreso del paciente a lo largo del seguimiento (RF-15): alertas, evolución y
 * adherencia, leídas de ROBLE.
 *
 * Lo primero que se ve son las **alertas**, porque es lo que el profesional necesita
 * enterarse sin buscar: un retroceso, días sin reportar, una indicación que no se
 * cumple, una urgencia. Las escriben el agente de seguimiento y la función de
 * recordatorios en `eventos`; aquí sólo se leen.
 *
 * Después, la **evolución** en el tiempo: la escala de 0 a 10 que la persona reporta,
 * como línea, con la franja de 3 o menos marcada porque es el umbral con el que el
 * sistema avisa (`ESCALA_PREOCUPANTE` en `seguimiento.py`). La gráfica no interpreta
 * nada: no dice «va mejorando». Eso lo concluye el profesional.
 */

import { useMemo, useRef, useState, type PointerEvent } from 'react';
import { bandaDeEscala, escalaVisible, fechaHora, hace } from '../formato';
import { esVerdad, idDe, type Adherencia, type EventoCaso, type Evolucion, type Indicacion } from '../tipos';
import { Tarjeta } from './Piezas';
import { IconoAlerta, IconoCampana, IconoTendencia } from './Iconos';

// ------------------------------------------------------------------ alertas

/** Los eventos de la bitácora que piden la atención del profesional, y cómo decirlos. */
const ALERTAS: Record<string, (detalle: Record<string, unknown>) => string> = {
  urgencia_escalada: () => 'Se activó la ruta de emergencia.',
  evolucion_desfavorable: (d) =>
    d.anterior !== null && d.anterior !== undefined
      ? `Reportó un retroceso: de ${d.anterior} a ${d.escala} en la escala.`
      : `Reportó ${d.escala} en la escala, en la franja de alerta.`,
  sin_evolucion: (d) => `Lleva ${d.dias ?? 'varios'} días sin contar cómo va.`,
  sin_adherencia: (d) => {
    const cuales = Array.isArray(d.indicaciones) ? d.indicaciones.map(String) : [];
    return cuales.length
      ? `Sin reportes de: ${cuales.join('; ')}.`
      : `Más de ${d.horas ?? 36} horas sin reportar si cumple sus indicaciones.`;
  },
  indicacion_no_cumplida: (d) =>
    d.motivo ? `No cumplió una indicación: «${String(d.motivo)}».` : 'No cumplió una indicación.',
};

export function esAlerta(evento: EventoCaso): boolean {
  return String(evento.tipo ?? '') in ALERTAS;
}

function detalleDe(evento: EventoCaso): Record<string, unknown> {
  const crudo = evento.detalle;
  if (crudo && typeof crudo === 'object') return crudo as Record<string, unknown>;
  if (typeof crudo === 'string') {
    try {
      const leido = JSON.parse(crudo);
      return leido && typeof leido === 'object' ? leido : {};
    } catch {
      return {};
    }
  }
  return {};
}

export function Alertas({ eventos }: { eventos: EventoCaso[] }) {
  const alertas = eventos
    .filter(esAlerta)
    .sort((a, b) => String(b.creado_en ?? '').localeCompare(String(a.creado_en ?? '')));

  return (
    <Tarjeta
      titulo="Alertas del seguimiento"
      icono={<IconoCampana />}
      extra={alertas.length > 0 ? <span className="cuenta">{alertas.length}</span> : undefined}
    >
      {alertas.length === 0 ? (
        <p className="fino">
          Sin alertas. Aquí aparecen los retrocesos, los silencios y las indicaciones que no se
          cumplen.
        </p>
      ) : (
        <ul className="alertas">
          {alertas.slice(0, 6).map((evento) => (
            <li key={idDe(evento)} className={`alerta s-${String(evento.severidad ?? 'info')}`}>
              {(evento.severidad === 'critica' || evento.severidad === 'alta') && (
                <IconoAlerta width={16} height={16} />
              )}
              <span className="texto">{ALERTAS[String(evento.tipo)]?.(detalleDe(evento))}</span>
              <span className="fino">{hace(evento.creado_en)}</span>
            </li>
          ))}
        </ul>
      )}
    </Tarjeta>
  );
}

// ---------------------------------------------------------------- evolución

interface Punto {
  clave: string;
  momento: number;
  escala: number;
  nota: string;
  cuando: string;
}

const ANCHO = 600;
const ALTO = 200;
const MARGEN = { arriba: 14, derecha: 28, abajo: 26, izquierda: 30 };
const UMBRAL = 3;

export function CurvaDeEvolucion({ filas }: { filas: Evolucion[] }) {
  const puntos = useMemo<Punto[]>(
    () =>
      filas
        .map((fila) => ({
          clave: idDe(fila),
          momento: new Date(String(fila.reportado_en ?? '')).getTime(),
          escala: Number(fila.escala),
          nota: String(fila.nota ?? ''),
          cuando: String(fila.reportado_en ?? ''),
        }))
        .filter((p) => Number.isFinite(p.momento) && Number.isFinite(p.escala))
        .sort((a, b) => a.momento - b.momento),
    [filas]
  );

  return (
    <Tarjeta titulo="Cómo ha ido" icono={<IconoTendencia />}>
      {puntos.length === 0 ? (
        <p className="fino">
          Todavía no ha reportado cómo va. El agente de seguimiento le pregunta en cada
          conversación, de 0 (peor que nunca) a 10 (como antes).
        </p>
      ) : (
        <>
          <GraficaDeEvolucion puntos={puntos} />
          <ul className="evolucion">
            {[...puntos]
              .reverse()
              .slice(0, 5)
              .map((p) => (
                <li key={p.clave}>
                  <span className={`escala ${bandaDeEscala(p.escala)}`}>{escalaVisible(p.escala)}</span>
                  <span className="texto">{p.nota}</span>
                  <span className="fino">{hace(p.cuando)}</span>
                </li>
              ))}
          </ul>
        </>
      )}
    </Tarjeta>
  );
}

/**
 * La línea de la escala en el tiempo, con una sola serie: sin leyenda, el título de
 * la tarjeta la nombra. Pasar el puntero (o el dedo) muestra el reporte más cercano;
 * la lista de debajo es la misma información en texto, para quien no ve la gráfica.
 */
function GraficaDeEvolucion({ puntos }: { puntos: Punto[] }) {
  const lienzo = useRef<SVGSVGElement>(null);
  const [activo, setActivo] = useState<number | null>(null);

  const primero = puntos[0];
  const ultimo = puntos[puntos.length - 1];
  if (!primero || !ultimo) return null;

  const izquierda = MARGEN.izquierda;
  const derecha = ANCHO - MARGEN.derecha;
  const arriba = MARGEN.arriba;
  const abajo = ALTO - MARGEN.abajo;

  const desde = primero.momento;
  const hasta = ultimo.momento;
  const x = (momento: number) =>
    hasta === desde ? (izquierda + derecha) / 2 : izquierda + ((momento - desde) / (hasta - desde)) * (derecha - izquierda);
  const y = (escala: number) => abajo - (Math.max(0, Math.min(10, escala)) / 10) * (abajo - arriba);

  const trazo = puntos.map((p, i) => `${i === 0 ? 'M' : 'L'}${x(p.momento).toFixed(1)},${y(p.escala).toFixed(1)}`).join(' ');
  const resumen =
    `Evolución: ${puntos.length} reporte${puntos.length === 1 ? '' : 's'}, ` +
    `el primero en ${escalaVisible(primero.escala)} y el último en ${escalaVisible(ultimo.escala)}.`;

  function alMover(evento: PointerEvent<SVGRectElement>) {
    const caja = lienzo.current?.getBoundingClientRect();
    if (!caja) return;
    const enX = ((evento.clientX - caja.left) / caja.width) * ANCHO;
    const distancias = puntos.map((p) => Math.abs(x(p.momento) - enX));
    setActivo(distancias.indexOf(Math.min(...distancias)));
  }

  const elegido = activo === null ? undefined : puntos[activo];

  return (
    <figure className="grafica-evolucion">
      <svg ref={lienzo} viewBox={`0 0 ${ANCHO} ${ALTO}`} role="img" aria-label={resumen}>
        {/* La franja de alerta: 3 o menos es lo que el sistema trata como preocupante. */}
        <rect className="franja-alerta" x={izquierda} y={y(UMBRAL)} width={derecha - izquierda} height={abajo - y(UMBRAL)} />
        <text className="rotulo-franja" x={derecha - 4} y={abajo - 6} textAnchor="end">
          franja de alerta (≤ {UMBRAL})
        </text>

        {[0, 5, 10].map((valor) => (
          <g key={valor}>
            <line className="guia" x1={izquierda} x2={derecha} y1={y(valor)} y2={y(valor)} />
            <text className="eje" x={izquierda - 8} y={y(valor) + 4} textAnchor="end">
              {valor}
            </text>
          </g>
        ))}

        <text className="eje" x={izquierda} y={ALTO - 6} textAnchor="start">
          {fechaCorta(primero.momento)}
        </text>
        {puntos.length > 1 && (
          <text className="eje" x={derecha} y={ALTO - 6} textAnchor="end">
            {fechaCorta(ultimo.momento)}
          </text>
        )}

        {elegido && (
          <line className="cruz" x1={x(elegido.momento)} x2={x(elegido.momento)} y1={arriba} y2={abajo} />
        )}

        <path className="linea" d={trazo} />
        {puntos.map((p, i) => (
          <circle
            key={p.clave}
            className={i === activo ? 'punto activo' : 'punto'}
            cx={x(p.momento)}
            cy={y(p.escala)}
            r={i === activo ? 6 : 4.5}
          />
        ))}

        {/* El último valor, rotulado al final de la línea: es el que más importa. */}
        <text className="valor-final" x={x(ultimo.momento) + 9} y={y(ultimo.escala) + 4}>
          {escalaVisible(ultimo.escala)}
        </text>

        {/* La zona de captura es todo el lienzo, no los puntos: un punto de 9 px es
            difícil de atinar con el dedo. */}
        <rect
          className="captura"
          x={0}
          y={0}
          width={ANCHO}
          height={ALTO}
          onPointerMove={alMover}
          onPointerDown={alMover}
          onPointerLeave={() => setActivo(null)}
        />
      </svg>

      {elegido && (
        <figcaption
          className="globo"
          style={{ left: `${(x(elegido.momento) / ANCHO) * 100}%` }}
          aria-live="polite"
        >
          <strong>{escalaVisible(elegido.escala)} de 10</strong> · {fechaHora(elegido.cuando)}
          {elegido.nota && <span>{elegido.nota}</span>}
        </figcaption>
      )}
    </figure>
  );
}

function fechaCorta(momento: number): string {
  return new Intl.DateTimeFormat('es-CO', { day: 'numeric', month: 'short', timeZone: 'America/Bogota' }).format(
    new Date(momento)
  );
}

// --------------------------------------------------------------- adherencia

/**
 * Cada indicación activa con lo que la persona ha reportado de ella: cuántas veces la
 * cumplió y una tira con los últimos reportes, el más reciente a la derecha.
 */
export function AdherenciaPorIndicacion({
  indicaciones,
  adherencias,
  alDesactivar,
}: {
  indicaciones: Indicacion[];
  adherencias: Adherencia[];
  alDesactivar: (indicacionId: string) => void;
}) {
  return (
    <ul className="indicaciones">
      {indicaciones
        .filter((indicacion) => esVerdad(indicacion.activa))
        .map((indicacion) => {
          const propias = adherencias
            .filter((fila) => String(fila.indicacion_id ?? '') === idDe(indicacion))
            .sort((a, b) => String(a.reportado_en ?? '').localeCompare(String(b.reportado_en ?? '')));
          const cumplidas = propias.filter((fila) => esVerdad(fila.cumplida)).length;
          const ultimo = propias[propias.length - 1];

          return (
            <li key={idDe(indicacion)}>
              <span className="texto">{String(indicacion.texto ?? '')}</span>
              <span className="fino">
                {String(indicacion.frecuencia || 'una vez')} ·{' '}
                {propias.length === 0
                  ? 'sin reportes'
                  : `${cumplidas} de ${propias.length} cumplidas · último ${hace(ultimo?.reportado_en)}`}
              </span>
              {propias.length > 0 && (
                <span className="tira" aria-hidden="true">
                  {propias.slice(-10).map((fila) => (
                    <span
                      key={idDe(fila)}
                      className={esVerdad(fila.cumplida) ? 'marca si' : 'marca no'}
                      title={`${esVerdad(fila.cumplida) ? 'Cumplida' : 'No cumplida'} · ${fechaHora(fila.reportado_en)}`}
                    />
                  ))}
                </span>
              )}
              <button type="button" className="enlace" onClick={() => alDesactivar(idDe(indicacion))}>
                Desactivar
              </button>
            </li>
          );
        })}
    </ul>
  );
}
