import { useEffect, useState } from 'react';
import { ScrollView, Text, View } from 'react-native';
import { fechaHoraDe } from '../agenda';
import { hayPermiso, pedirPermiso } from '../notificaciones';
import type { Aviso } from '../avisos';
import { Boton, Etiqueta, Tarjeta } from '../piezas';
import { estilosDe, useColores } from '../tema';

const NOMBRE: Record<Aviso['origen'], string> = {
  toma: 'Tu plan',
  cita: 'Cita',
  recordatorio: 'Recordatorio',
};

export function Avisos({ avisos, alActivar }: { avisos: Aviso[]; alActivar: () => void }) {
  const c = useColores();
  const e = estilosDe(c);
  const [permiso, setPermiso] = useState<boolean | null>(null);

  useEffect(() => {
    void hayPermiso().then(setPermiso);
  }, []);

  return (
    <ScrollView contentContainerStyle={{ padding: 16, gap: 12 }}>
      {permiso === false ? (
        <Tarjeta titulo="Activa los avisos">
          <Text style={e.texto}>Así te avisamos a la hora, sin que tengas que abrir la app.</Text>
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

      <Tarjeta titulo="Próximos avisos">
        {avisos.length === 0 ? (
          <Text style={e.fino}>No hay avisos programados en los próximos días.</Text>
        ) : (
          avisos.slice(0, 30).map((aviso) => (
            <View
              key={aviso.clave}
              style={{ borderTopWidth: 1, borderTopColor: c.borde, paddingTop: 10, gap: 4 }}
            >
              <View style={{ flexDirection: 'row', justifyContent: 'space-between', gap: 8 }}>
                <Text style={[e.fino, { flex: 1 }]}>{fechaHoraDe(aviso.momento)}</Text>
                <Etiqueta texto={NOMBRE[aviso.origen]} />
              </View>
              <Text style={e.texto}>{aviso.origen === 'cita' ? `${aviso.titulo}: ${aviso.cuerpo}` : aviso.cuerpo}</Text>
            </View>
          ))
        )}
      </Tarjeta>

      <Text style={[e.fino, { textAlign: 'center' }]}>
        La lista se renueva cada vez que abres la app.
      </Text>
    </ScrollView>
  );
}
