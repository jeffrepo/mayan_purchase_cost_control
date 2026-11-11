/** @odoo-module **/

import { registry } from "@web/core/registry";
import { _t } from "@web/core/l10n/translation";
import { useService } from "@web/core/utils/hooks";
import {
    ProductLabelSectionAndNoteOne2Many,
    productLabelSectionAndNoteOne2Many,
} from "@account/components/product_label_section_and_note_field/product_label_section_and_note_field";

export class MayanCostOrderLines extends ProductLabelSectionAndNoteOne2Many {
    setup() {
        super.setup();
        this.notification = useService("notification");
    }

    async onAdd(params = {}) {
        // Commit the text currently being edited before inspecting its justification.
        const proms = [];
        this.list.model.bus.trigger("NEED_LOCAL_CHANGES", { proms });
        await Promise.all(proms);
        if (this.list.editedRecord) {
            await this.list.editedRecord._updatePromise;
        }
        const pending = this.list.records.find(({ data }) =>
            !data.display_type && data.mayan_requires_justification &&
            !(data.mayan_cost_justification || "").trim()
        );
        if (pending) {
            this.notification.add(_t(
                "Completa la justificación de %s antes de agregar otra línea.",
                pending.data.product_id?.[1] || pending.data.name || _t("este producto")
            ), { type: "warning" });
            return;
        }
        return super.onAdd(params);
    }
}

registry.category("fields").add("mayan_cost_order_lines", {
    ...productLabelSectionAndNoteOne2Many,
    component: MayanCostOrderLines,
});
