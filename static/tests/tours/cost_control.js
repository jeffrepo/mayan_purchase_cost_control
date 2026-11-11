/** @odoo-module **/
import { registry } from "@web/core/registry";

registry.category("web_tour.tours").add("mayan_cost_control_justification", {
    steps: () => [
        { trigger: ".o_data_row td[name='price_unit']", run: "click" },
        { trigger: ".o_field_widget[name='price_unit'] input", run: "edit 13" },
        { trigger: ".o_field_x2many_list_row_add a:first", run: "click" },
        {
            trigger: ".o_notification_content:contains('justificación')",
            run() {
                if (document.querySelectorAll(".o_data_row td[name='product_id']").length !== 1) {
                    throw new Error("Una línea sin justificación permitió agregar otro producto");
                }
            },
        },
        { trigger: ".o_field_widget[name='mayan_cost_justification'] textarea", run: "edit Cotización urgente del proveedor" },
        { trigger: ".o_field_x2many_list_row_add a:first", run: "click" },
        {
            trigger: ".o_data_row:nth-child(2) .o_field_widget[name='product_id'] input",
            run() {
                if (document.querySelectorAll(".o_data_row td[name='product_id']").length !== 2) {
                    throw new Error("No se pudo continuar después de justificar");
                }
            },
        },
        { trigger: ".o_data_row:nth-child(2) .o_list_record_remove", run: "click" },
        { trigger: ".o_form_button_save", run: "click" },
        { trigger: "body:has(.o_form_status_indicator_buttons.invisible)", run() {} },
    ],
});
