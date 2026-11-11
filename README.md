# Mayan - Control de costos de compra

Addon para **Odoo 18**, desarrollo No. 7. La raíz del repositorio es directamente
el addon `mayan_purchase_cost_control`.

## Requisitos e instalación

1. Actualizar `purchase_request_app` a **18.0.1.6.0** o posterior. Esta versión
   prepara precios con unidad, moneda e impuestos correctos y ofrece el método
   que permite vincular cada línea generada con la solicitud.
2. Colocar ambos repositorios en `addons_path`, reiniciar Odoo y actualizar la
   aplicación de solicitudes antes de instalar **Mayan - Control de costos de compra**.
3. En **Compras > Configuración > Categorías de productos**, marcar
   **Solicitud de compra obligatoria** en las categorías correspondientes.
   Se aplica a la compañía activa y a todas sus subcategorías; una subcategoría
   sin marcar no elimina la obligación heredada.
4. Los compradores que consultan solicitudes deben tener el grupo existente
   **Solicitud de compra**, además de sus permisos de Compras e Inventario.

```bash
odoo-bin -d NOMBRE_BD -u purchase_request_app -i mayan_purchase_cost_control --stop-after-init
```

## Comparación por línea

Se muestran costo promedio/referencia, precio neto sin impuestos, diferencia
unitaria, variación porcentual, estado y justificación. Los importes se expresan
en la **moneda y unidad de medida de la orden**.

```text
diferencia = precio neto unitario sin impuestos - costo de referencia
variación (%) = diferencia / costo de referencia × 100
```

- El precio neto considera el descuento y los impuestos incluidos, mediante el
  motor fiscal de Odoo; no se divide un subtotal redondeado entre cantidades.
- El costo es `standard_price` del producto en la compañía de la compra. Es el
  costo promedio de inventario para categorías configuradas con **Costo promedio
  (AVCO)**. Para FIFO o costo estándar representa el costo vigente del producto;
  el módulo no cambia el método de valoración ni inventa un promedio distinto.
- La conversión de moneda usa la fecha de la orden. El costo por unidad de
  inventario se convierte a la unidad de compra (por ejemplo, unidad a docena).
- **Exactamente -20% y +20% están permitidos** sin justificación. La comparación
  utiliza seis decimales porcentuales para evitar errores de coma flotante.
- Fuera del rango se exige una justificación con texto; espacios o saltos de línea
  solos no son válidos. No se agrega un flujo de autorización gerencial.
- Con costo cero o negativo se muestra **Sin costo de referencia**, se oculta el
  porcentaje y se exige justificación. No se divide entre cero.
- Se aplica a productos y servicios; las secciones y notas quedan excluidas.

El formulario exige justificar antes de agregar otra línea. El servidor valida
también creaciones, ediciones, importaciones, llamadas API, catálogo y confirmación,
incluida la aprobación estándar de Odoo si la compañía ya la utiliza.

La generación automática desde una solicitud puede dejar un **borrador** pendiente
de justificación cuando todavía no existe costo. Esto permite completar el motivo
en la propia orden. Ese borrador no admite más productos ni confirmación hasta
completar los motivos. No se generan justificaciones automáticas.

## Historial y cambios

El costo se consulta en vivo mientras la orden está en borrador y se valida de
nuevo al confirmar. Al confirmar queda guardado sin redondeo monetario, por lo que
las recepciones posteriores no cambian la comparación histórica.

Cada justificación registra usuario, fecha, producto, motivo e importes en el
historial de la orden. Cambiar producto, unidad, precio, descuento o impuestos
requiere justificar de nuevo si el resultado sigue fuera del rango. Cambiar
compañía, moneda o fecha reinicia la referencia y los motivos. Cambiar únicamente
la cantidad conserva la justificación. Una copia no reutiliza motivos ni auditoría:
si continúa fuera del rango, se debe crear con una nueva justificación.

La cancelación permanece disponible para órdenes pendientes. No se modifican
recepciones, asientos, métodos de valoración ni facturas de forma automática.
Al regresar una orden a borrador se descarta la referencia congelada y se exige
una nueva justificación si corresponde; los motivos anteriores siguen en el historial.

## Solicitudes obligatorias

Las categorías marcadas no permiten guardar una orden sin `purchase_request_id`.
La solicitud debe pertenecer a la compañía, no estar cancelada y contener una línea
de compra de ese producto para el proveedor, con cantidad positiva. Un texto libre
en **Documento origen** no sustituye el vínculo.

Las compras nuevas generadas desde solicitudes conservan también la línea exacta
en **Línea de solicitud**. Se valida que coincida con solicitud, producto y proveedor.
Las órdenes históricas que solo tienen el vínculo del encabezado se validan contra
los productos/proveedores solicitados; no se asignan líneas antiguas por suposición.
No se exige retrospectivamente un motivo a compras ya confirmadas mientras no se
modifiquen sus datos comerciales. Las nuevas reglas se comprueban al editar o
confirmar las órdenes afectadas. No se limitan cantidades a lo solicitado: ese
control no forma parte del desarrollo No. 7.

## Pruebas

La integración continua usa Odoo 18 y PostgreSQL 16. Ejecuta por separado las
pruebas de la dependencia y las de este módulo, incluyendo un recorrido real del
formulario en Chrome. La dependencia se fija a un commit revisado en el workflow.

```bash
odoo-bin -d mayan_cost_test -i mayan_purchase_cost_control --without-demo=all \
  --test-enable --test-tags=/mayan_purchase_cost_control --stop-after-init
```

Cobertura: límites positivos/negativos, impuestos y descuentos, unidades y monedas,
compañías, costo inexistente, auditoría, manipulación por API/contexto, categorías
descendientes, solicitudes incorrectas, costos históricos después de recibir,
compradores sin rol gerencial y bloqueo del ingreso de líneas en el navegador.

Validar en una copia de la base Mayan antes de instalar en producción, con sus
categorías AVCO, monedas, impuestos y permisos reales.
