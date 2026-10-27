/** @odoo-module **/

/**
 * DJI - Avisos en pedido de venta
 *
 * Muestra popup informativo (no bloqueante) al guardar un pedido cuando:
 *  1. El cliente tiene días de servicio configurados → indica próxima entrega
 *  2. La base del pedido es inferior a 90 €
 *
 * Estrategia: patch del método save del FormController de ventas.
 */

import { patch } from '@web/core/utils/patch';
import { FormController } from '@web/views/form/form_controller';
import { useService } from '@web/core/utils/hooks';
import { _t } from '@web/core/l10n/translation';

// Solo parcheamos si estamos en un formulario de sale.order
// (el patch es global, así que filtramos por modelo dentro)

patch(FormController.prototype, {
    setup() {
        super.setup(...arguments);
        // Guardamos referencia al servicio de notificaciones
        try {
            this._djiNotification = useService('notification');
        } catch {
            this._djiNotification = null;
        }
    },

    async save(options = {}) {
        // Llamar al save original
        const result = await super.save(...arguments);

        // Solo actuar en sale.order
        if (this.props?.resModel !== 'sale.order') {
            return result;
        }

        // Solo si el guardado fue exitoso y tenemos ID de registro
        const resId = this.model?.root?.resId;
        if (!resId) return result;

        // Obtener avisos desde el servidor
        try {
            const orm = this.env.services.orm;
            const avisos = await orm.call(
                'sale.order',
                'get_avisos_pedido',
                [],
                { order_id: resId }
            );

            const notif = this._djiNotification;
            if (!notif) return result;

            if (avisos.aviso_entrega) {
                notif.add(avisos.aviso_entrega, {
                    title: _t('📦 Entrega programada'),
                    type: 'info',
                    sticky: false,
                    className: 'dji-notif-entrega',
                });
            }

            if (avisos.aviso_minimo) {
                notif.add(avisos.aviso_minimo, {
                    title: _t('⚠️ Pedido mínimo'),
                    type: 'warning',
                    sticky: true,   // El de mínimo se queda hasta que el usuario lo cierre
                    className: 'dji-notif-minimo',
                });
            }
        } catch (e) {
            // No interrumpir el flujo si falla el aviso
            console.warn('[DJI] Error al obtener avisos del pedido:', e);
        }

        return result;
    },
});
