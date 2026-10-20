from odoo import models

# Informes de serie que se pintan con el diseño DJI. Se mantiene su nombre
# técnico (Imprimir, Enviar, el portal y Copiloto lo piden por ese nombre) y
# solo se cambia la plantilla con la que se dibujan. Así no hay que heredar las
# plantillas de serie, que otros módulos de la instalación ya modifican.
FACTURAS = {'account.report_invoice', 'account.report_invoice_with_payments'}
PRESUPUESTOS = {'sale.report_saleorder', 'sale.report_saleorder_raw'}


class IrActionsReport(models.Model):
    _inherit = 'ir.actions.report'

    def _render_template(self, template, values=None):
        docs = (values or {}).get('docs')
        modelo = getattr(docs, '_name', None)
        if docs:
            if template in FACTURAS and modelo == 'account.move' \
                    and all(m.move_type in ('out_invoice', 'out_refund') for m in docs):
                template = 'dji_documentos.report_factura'
            elif template in PRESUPUESTOS and modelo == 'sale.order':
                template = 'dji_documentos.report_presupuesto'
        return super()._render_template(template, values)
