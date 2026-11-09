/**
 * Los avisos de los próximos días, agrupados por día.
 *
 * Antes era una sola lista donde cada fila repetía la fecha completa («miércoles, 11 de
 * noviembre, 7:00 a. m.») y la etiqueta «Tu plan»: treinta filas casi iguales. Ahora el
 * día va una vez como título, cada fila lleva sólo la hora, y la etiqueta queda para lo
 * que no es una toma —una cita, un recordatorio—, que es lo que hay que distinguir.
 */

import { useEffect, useState } from 'react';
import { Text, View } from 'react-native';
import { horaDe } from '../agenda';
import type { Aviso } from '../avisos';
import { hayPermiso, pedirPermiso } from '../notificaciones';
import { Boton, Desplazable, Etiqueta, Seccion, Tarjeta } from '../piezas';
import { estilosDe, F, S, T, useColores } from '../tema';

const NOMBRE: Partial<Record<Aviso['origen'], string>> = {
  cita: 'Cita',
  recordatorio: 'Recordatorio',
};

const DIA = 24 * 60 * 60 * 1000;

export function Avisos({ avisos, alActivar }: { avisos: Aviso[]; alActivar: () => void }) {
  const c = useColores();
  const e = estilosDe(c);
  const [permiso, setPermiso] = useState<boolean | null>(null);

  useEffect(() => {
    void hayPermiso().then(setPermiso);
  }, []);

  const dias = porDia(avisos.slice(0, 30));

  return (
    <Desplazable>
      {permiso === false ? (
        <Tarjeta titulo="Activa los avisos">
          <Text style={e.texto}>Así te avisamos a la hora de cada toma y antes de tus citas, sin abrir la app.</Text>
          <Boton
            texto="Activar avisos"
            alPulsar={() =>
              void pedirPermiso().then((concedido) => {
                setPermiso(concedido);
                if (concedido) alActivar();
              })
            }
          />
        </Tarjeta>
      ) : null}

      {dias.length === 0 ? (
        <Tarjeta titulo="Sin avisos por ahora">
          <Text style={e.fino}>Cuando tu plan tenga tomas o citas en los próximos días, aparecen aquí.</Text>
        </Tarjeta>
      ) : (
        dias.map(([dia, lista]) => (
          <Seccion
            key={dia}
            titulo={dia}
            extra={<Text style={e.pie}>{lista.length} {lista.length === 1 ? 'aviso' : 'avisos'}</Text>}
          >
            {lista.map((aviso) => {
              const etiqueta = NOMBRE[aviso.origen];
              return (
                <View key={aviso.clave} style={{ flexDirection: 'row', gap: S.m }}>
                  <Text numberOfLines={1} style={{ width: 84, color: c.primario, fontSize: T.fino, lineHeight: 23, fontFamily: F.negrita }}>
                    {horaDe(aviso.momento)}
                  </Text>
                  <View style={{ flex: 1, gap: S.xs, alignItems: 'flex-start' }}>
                    <Text style={e.texto}>{aviso.origen === 'cita' ? aviso.titulo : aviso.cuerpo}</Text>
                    {aviso.origen === 'cita' ? <Text style={e.fino}>{aviso.cuerpo}</Text> : null}
                    {etiqueta ? <Etiqueta tono="ambar" texto={etiqueta} /> : null}
                  </View>
                </View>
              );
            })}
          </Seccion>
        ))
      )}

      <Text style={[e.pie, { textAlign: 'center' }]}>La lista se actualiza cada vez que abres la app.</Text>
    </Desplazable>
  );
}

/** Agrupa por día de Bogotá, con «Hoy» y «Mañana» en vez de la fecha. */
function porDia(avisos: Aviso[]): [string, Aviso[]][] {
  const clave = (momento: Date) =>
    momento.toLocaleDateString('es-CO', { timeZone: 'America/Bogota', year: 'numeric', month: '2-digit', day: '2-digit' });
  const hoy = clave(new Date());
  const manana = clave(new Date(Date.now() + DIA));

  const grupos = new Map<string, Aviso[]>();
  for (const aviso of [...avisos].sort((a, b) => a.momento.getTime() - b.momento.getTime())) {
    const k = clave(aviso.momento);
    const titulo =
      k === hoy
        ? 'Hoy'
        : k === manana
          ? 'Mañana'
          : capitalizar(
              aviso.momento.toLocaleDateString('es-CO', {
                timeZone: 'America/Bogota',
                weekday: 'long',
                day: 'numeric',
                month: 'long',
              })
            );
    grupos.set(titulo, [...(grupos.get(titulo) ?? []), aviso]);
  }
  return [...grupos.entries()];
}

function capitalizar(texto: string): string {
  return texto.charAt(0).toUpperCase() + texto.slice(1);
}
