# DJI · Comprobación de tarifas de proveedor (Odoo 19)

Compara los precios de los pedidos de compra con la tarifa vigente del proveedor guardada en la app de Tarifas de Proveedores (Supabase).

## Qué hace
- **En tiempo real**: al meter o cambiar una línea (artículo, precio, unidad, descuento) marca la columna *Tarifa*: Correcto, Distinto, Sin tarifa o Sin precio, con el precio de tarifa y la diferencia en %.
- **Botón "Comprobar tarifa"**: vuelve a leer la tarifa y comprueba todo el pedido. Arriba sale un aviso con el resumen.
- **Botón "Aplicar precios de tarifa"**: pone el precio de tarifa en las líneas distintas (respeta el descuento) y lo anota en el historial.
- **Al confirmar el pedido**: si hay precios distintos, deja una nota en el historial. Nunca bloquea.

## Cómo encuentra la línea de tarifa de cada artículo
1. El vínculo hecho en la app (Comparar con Odoo).
2. El código del proveedor de la pestaña Compra del artículo = referencia de la tarifa.
3. El código de barras = EAN de la tarifa.

El precio se compara en la misma unidad de la línea: Caja → precio de caja; kg → precio por kg; Unidades → precio por unidad.
Si la unidad no lo deja claro, se usa el precio de tarifa más cercano.

## Configuración
Compras → Configuración → Ajustes → **Tarifas de proveedores**:
- URL de Supabase y clave **service_role** (Supabase → Project Settings → API).
- Empresa: DJI.
- Tolerancia: % de diferencia que se acepta como correcto (por defecto 1 %).
- Botón *Probar conexión*.

Requiere ejecutar antes en Supabase el archivo `supabase/04_odoo_pedidos.sql` de la app de Tarifas.
