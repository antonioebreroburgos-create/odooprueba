/** @odoo-module **/

import { registry } from '@web/core/registry';
import { useService } from '@web/core/utils/hooks';
import { Component, useState, onMounted, xml } from '@odoo/owl';

const DIAS = [
    { key: 'lunes',     label: 'Lunes' },
    { key: 'martes',    label: 'Martes' },
    { key: 'miercoles', label: 'Miércoles' },
    { key: 'jueves',    label: 'Jueves' },
    { key: 'viernes',   label: 'Viernes' },
    { key: 'sabado',    label: 'Sábado' },
    { key: 'domingo',   label: 'Domingo' },
    { key: 'sin_dia',   label: 'Sin día' },
];

function storageKey(uid) {
    return `dji_planificador_filtro_${uid}`;
}

function loadFiltro(uid) {
    try {
        const raw = localStorage.getItem(storageKey(uid));
        return raw ? JSON.parse(raw) : { rutaId: '', dia: '', zonaId: 0, modoDia: 'tags' };
    } catch { return { rutaId: '', dia: '', zonaId: 0, modoDia: 'tags' }; }
}

function saveFiltro(uid, data) {
    try {
        localStorage.setItem(storageKey(uid), JSON.stringify(data));
    } catch {}
}

class DjiPlanificador extends Component {
    static template = xml`
<div id="dji_planificador_root">
    <div class="dji-plan-header">
        <h2>🗓️ Planificador de Rutas <span style="font-size:11px;font-weight:400;color:#adb5bd;margin-left:6px">v1.3.1</span></h2>

        <!-- Filtro repartidor -->
        <select class="dji-plan-select" t-on-change="onRutaChange">
            <option value="">— Todos los repartidores —</option>
            <t t-foreach="state.rutas" t-as="r" t-key="r.id">
                <option t-att-value="r.id" t-att-selected="state.rutaId == r.id">
                    <t t-esc="r.name"/> (<t t-esc="r.count"/>)
                </option>
            </t>
        </select>

        <!-- Filtro zona -->
        <select class="dji-plan-select" t-on-change="onZonaChange"
                t-if="state.zonas.length > 0">
            <option value="0">— Todas las zonas —</option>
            <t t-foreach="state.zonas" t-as="z" t-key="z.id">
                <option t-att-value="z.id" t-att-selected="state.zonaId == z.id">
                    <t t-esc="z.name"/> (<t t-esc="z.count"/>)
                </option>
            </t>
        </select>

        <!-- Modo día -->
        <label class="dji-modo-label">
            <input type="checkbox"
                   t-att-checked="state.modoDia === 'partner'"
                   t-on-change="onModoDiaChange"/>
            Días por cliente
        </label>
    </div>

    <div class="dji-dias-bar">
        <button class="dji-dia-btn"
                t-att-class="state.dia === '' ? 'active' : ''"
                t-on-click="() => this.setDia('')">
            Todos
        </button>
        <t t-foreach="dias" t-as="d" t-key="d.key">
            <button class="dji-dia-btn"
                    t-att-class="(state.dia === d.key ? 'active ' : '') + (d.key === 'sin_dia' ? 'sin-dia' : '')"
                    t-on-click="() => this.setDia(d.key)">
                <t t-esc="d.label"/>
                <t t-if="state.counts[d.key]">
                    <span class="dji-count-badge"><t t-esc="state.counts[d.key]"/></span>
                </t>
            </button>
        </t>
    </div>

    <div class="dji-plan-stats" t-if="!state.loading">
        <strong><t t-esc="state.pedidos.length"/></strong> presupuestos
        <t t-if="state.zonaId"> · <span class="dji-badge-zona"><t t-esc="zonaLabel"/></span></t>
        <t t-if="state.dia"> · <t t-esc="diaLabel"/></t>
        <t t-if="state.modoDia === 'partner'">
            <span class="dji-badge-modo"> · días por cliente</span>
        </t>
    </div>

    <div class="dji-spinner" t-if="state.loading">⏳ Cargando...</div>

    <t t-if="!state.loading">
        <t t-if="state.pedidos.length === 0">
            <div class="dji-empty">📋 No hay presupuestos con estos filtros</div>
        </t>
        <t t-else="">
            <table class="dji-plan-tabla">
                <thead>
                    <tr>
                        <th>Pedido</th>
                        <th class="dji-th-sort" t-on-click="() => this.onSort('partner')">
                            Cliente <span class="dji-sort-icon"><t t-esc="sortIcon('partner')"/></span>
                        </th>
                        <th class="dji-th-sort" t-on-click="() => this.onSort('city')">
                            Ciudad <span class="dji-sort-icon"><t t-esc="sortIcon('city')"/></span>
                        </th>
                        <th>Zona</th>
                        <th>Importe</th>
                        <th>Día</th>
                        <th>Repartidor</th>
                        <th>Otras etiquetas</th>
                    </tr>
                </thead>
                <tbody>
                    <t t-foreach="pedidosOrdenados" t-as="p" t-key="p.id">
                        <tr>
                            <td>
                                <a class="dji-pedido-link"
                                   t-att-href="'/odoo/sales/' + p.id"
                                   target="_blank">
                                    <t t-esc="p.name"/>
                                </a>
                            </td>
                            <td class="dji-partner-name">
                                <t t-esc="p.partner"/>
                                <t t-if="p.commercial_name">
                                    <br/><span class="dji-commercial-name"><t t-esc="p.commercial_name"/></span>
                                </t>
                            </td>
                            <td class="dji-city"><t t-esc="p.city"/></td>
                            <td class="dji-zona-cell">
                                <t t-if="p.zona_name">
                                    <span class="dji-badge-zona-sm"><t t-esc="p.zona_name"/></span>
                                </t>
                            </td>
                            <td class="dji-importe">
                                <t t-esc="formatImporte(p.amount, p.currency)"/>
                            </td>
                            <td>
                                <select class="dji-select-inline"
                                        t-att-data-order-id="p.id"
                                        t-on-change="(ev) => this.onDiaChange(ev, p.id)">
                                    <option value="">— Sin día —</option>
                                    <t t-foreach="diasSinSinDia" t-as="d" t-key="d.key">
                                        <option t-att-value="d.key"
                                                t-att-selected="p.dia_tags.includes(d.key)">
                                            <t t-esc="d.label"/>
                                        </option>
                                    </t>
                                </select>
                                <span class="dji-saved-flash" t-att-id="'flash_dia_' + p.id">✓</span>
                            </td>
                            <td>
                                <select class="dji-select-inline"
                                        t-att-data-order-id="p.id"
                                        t-on-change="(ev) => this.onRutaPedidoChange(ev, p.id)">
                                    <option value="">— Sin ruta —</option>
                                    <t t-foreach="state.rutas" t-as="r" t-key="r.id">
                                        <option t-att-value="r.id"
                                                t-att-selected="p.ruta_ids.includes(r.id)">
                                            <t t-esc="r.name"/>
                                        </option>
                                    </t>
                                </select>
                                <span class="dji-saved-flash" t-att-id="'flash_ruta_' + p.id">✓</span>
                            </td>
                            <td>
                                <t t-foreach="otrasEtiquetas(p)" t-as="tag" t-key="tag">
                                    <span class="dji-tag"><t t-esc="tag"/></span>
                                </t>
                            </td>
                        </tr>
                    </t>
                </tbody>
            </table>
        </t>
    </t>
</div>`;

    static props = ['*'];

    setup() {
        this.orm = useService('orm');
        this.dias = DIAS;
        this.diasSinSinDia = DIAS.filter(d => d.key !== 'sin_dia');
        this.state = useState({
            rutas: [],
            rutaId: '',
            dia: '',
            zonaId: 0,
            modoDia: 'tags',
            pedidos: [],
            loading: true,
            counts: {},
            zonas: [],
            sortField: '',
            sortDir: 'asc',
        });
        onMounted(() => this.init());
    }

    get diaLabel() {
        return DIAS.find(d => d.key === this.state.dia)?.label || '';
    }

    get zonaLabel() {
        const z = this.state.zonas.find(z => z.id == this.state.zonaId);
        return z ? z.name : '';
    }

    formatImporte(amount, currency) {
        return (amount || 0).toLocaleString('es-ES', { minimumFractionDigits: 2 }) + ' ' + (currency || '€');
    }

    get pedidosOrdenados() {
        const { pedidos, sortField, sortDir } = this.state;
        if (!sortField) return pedidos;
        return [...pedidos].sort((a, b) => {
            const va = (a[sortField] || '').toLowerCase();
            const vb = (b[sortField] || '').toLowerCase();
            const cmp = va.localeCompare(vb, 'es');
            return sortDir === 'asc' ? cmp : -cmp;
        });
    }

    onSort(field) {
        if (this.state.sortField === field) {
            this.state.sortDir = this.state.sortDir === 'asc' ? 'desc' : 'asc';
        } else {
            this.state.sortField = field;
            this.state.sortDir = 'asc';
        }
    }

    sortIcon(field) {
        if (this.state.sortField !== field) return '⇅';
        return this.state.sortDir === 'asc' ? '↑' : '↓';
    }

    otrasEtiquetas(p) {
        const DIAS_KEYS = DIAS.map(d => d.key);
        return (p.tags || []).filter(t => {
            const norm = t.toLowerCase()
                .replace(/[éèê]/g,'e').replace(/[áàâ]/g,'a')
                .replace(/[óòô]/g,'o').replace(/[íìî]/g,'i')
                .replace(/[úùû]/g,'u').replace(/ñ/g,'n').trim();
            return !DIAS_KEYS.includes(norm);
        });
    }

    async init() {
        this.state.loading = true;
        const uid = odoo.session_info?.uid || odoo.uid || 'default';
        const filtro = loadFiltro(uid);
        this.state.rutaId = filtro.rutaId || '';
        this.state.dia    = filtro.dia    || '';
        this.state.zonaId = filtro.zonaId || 0;
        this.state.modoDia = filtro.modoDia || 'tags';

        const [rutas, zonas] = await Promise.all([
            this.orm.call('dji.planificador.rutas', 'get_rutas', [], {}),
            this.orm.call('dji.planificador.rutas', 'get_zonas', [], {}).catch(() => []),
        ]);
        this.state.rutas = rutas;
        this.state.zonas = zonas;

        await this.cargarPedidos();
    }

    async cargarPedidos() {
        this.state.loading = true;
        const pedidos = await this.orm.call('dji.planificador.rutas', 'get_pedidos', [], {
            ruta_id:  this.state.rutaId || null,
            dia:      this.state.dia    || null,
            zona_id:  this.state.zonaId || null,
            modo_dia: this.state.modoDia,
        });
        this.state.pedidos = pedidos;

        const counts = {};
        let base = pedidos;
        if (this.state.dia) {
            base = await this.orm.call('dji.planificador.rutas', 'get_pedidos', [], {
                ruta_id:  this.state.rutaId || null,
                dia:      null,
                zona_id:  this.state.zonaId || null,
                modo_dia: this.state.modoDia,
            });
        }
        for (const d of DIAS) {
            const campo = this.state.modoDia === 'partner' ? 'partner_dias' : 'dia_tags';
            if (d.key === 'sin_dia') {
                counts[d.key] = base.filter(p => !(p[campo] || []).length).length;
            } else {
                counts[d.key] = base.filter(p => (p[campo] || []).includes(d.key)).length;
            }
        }
        this.state.counts = counts;
        this.state.loading = false;
    }

    _guardarFiltro() {
        const uid = odoo.session_info?.uid || odoo.uid || 'default';
        saveFiltro(uid, {
            rutaId: this.state.rutaId,
            dia:    this.state.dia,
            zonaId: this.state.zonaId,
            modoDia: this.state.modoDia,
        });
    }

    async onRutaChange(ev) {
        this.state.rutaId = ev.target.value ? parseInt(ev.target.value) : '';
        this._guardarFiltro();
        await this.cargarPedidos();
    }

    async onZonaChange(ev) {
        this.state.zonaId = ev.target.value ? parseInt(ev.target.value) : 0;
        this._guardarFiltro();
        await this.cargarPedidos();
    }

    async onModoDiaChange(ev) {
        this.state.modoDia = ev.target.checked ? 'partner' : 'tags';
        this._guardarFiltro();
        await this.cargarPedidos();
    }

    async setDia(dia) {
        this.state.dia = dia;
        this._guardarFiltro();
        await this.cargarPedidos();
    }

    async onDiaChange(ev, orderId) {
        const dia = ev.target.value;
        await this.orm.call('dji.planificador.rutas', 'set_dia_pedido', [],
            { order_id: orderId, dia_nuevo: dia });
        this.flashSaved('flash_dia_' + orderId);
        const p = this.state.pedidos.find(x => x.id === orderId);
        if (p) {
            const DIAS_KEYS = DIAS.map(d => d.key);
            p.dia_tags = dia ? [dia] : [];
            p.tags = p.tags.filter(t => {
                const norm = t.toLowerCase()
                    .replace(/[éèê]/g,'e').replace(/[áàâ]/g,'a')
                    .replace(/[óòô]/g,'o').replace(/[íìî]/g,'i')
                    .replace(/[úùû]/g,'u').replace(/ñ/g,'n').trim();
                return !DIAS_KEYS.includes(norm);
            });
            if (dia) {
                const label = DIAS.find(d => d.key === dia)?.label || dia;
                p.tags.push(label);
            }
        }
    }

    async onRutaPedidoChange(ev, orderId) {
        const rutaId = ev.target.value ? parseInt(ev.target.value) : null;
        await this.orm.call('dji.planificador.rutas', 'set_ruta_pedido', [],
            { order_id: orderId, ruta_id: rutaId });
        this.flashSaved('flash_ruta_' + orderId);
        const p = this.state.pedidos.find(x => x.id === orderId);
        if (p) p.ruta_ids = rutaId ? [rutaId] : [];
    }

    flashSaved(id) {
        const el = document.getElementById(id);
        if (!el) return;
        el.classList.add('show');
        setTimeout(() => el.classList.remove('show'), 1500);
    }
}

registry.category('actions').add('dji_planificador_rutas', DjiPlanificador);

export { DjiPlanificador };
