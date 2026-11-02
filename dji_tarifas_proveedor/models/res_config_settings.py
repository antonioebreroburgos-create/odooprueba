from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    tarifas_supabase_url = fields.Char('URL de Supabase', config_parameter='tarifas_proveedor.supabase_url')
    tarifas_supabase_key = fields.Char('Clave service_role', config_parameter='tarifas_proveedor.supabase_key')
    tarifas_empresa = fields.Selection([('DJI', 'DJI'), ('SYL', 'Sylonuba')], string='Empresa en la app de Tarifas',
                                       config_parameter='tarifas_proveedor.empresa', default='DJI')
    tarifas_tolerancia = fields.Float('Tolerancia (%)', config_parameter='tarifas_proveedor.tolerancia', default=1.0)

    def action_probar_tarifas(self):
        """Comprueba que la conexión con la app de Tarifas funciona."""
        self.execute()
        import requests
        icp = self.env['ir.config_parameter'].sudo()
        url = (icp.get_param('tarifas_proveedor.supabase_url') or '').rstrip('/')
        key = icp.get_param('tarifas_proveedor.supabase_key') or ''
        try:
            r = requests.post(f"{url}/rest/v1/rpc/tarifa_para_odoo", json={'p_empresa': icp.get_param('tarifas_proveedor.empresa') or 'DJI', 'p_partner_id': 0},
                              headers={'apikey': key, 'Authorization': f"Bearer {key}"}, timeout=10)
            ok = r.status_code == 200
            mensaje = 'Conexión correcta con la app de Tarifas.' if ok else f'La app de Tarifas respondió {r.status_code}: {r.text[:200]}'
        except Exception as e:
            ok, mensaje = False, f'No se pudo conectar: {e}'
        return {'type': 'ir.actions.client', 'tag': 'display_notification',
                'params': {'title': 'Tarifas de proveedores', 'message': mensaje, 'type': 'success' if ok else 'danger', 'sticky': not ok}}
