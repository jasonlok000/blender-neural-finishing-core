# SPDX-FileCopyrightText: 2026 Jason Lok
# SPDX-License-Identifier: GPL-2.0-or-later
from bpy.types import Panel


class RENDER_PT_neural_finishing(Panel):
    bl_label = "Neural Finishing (Experimental)"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "render"
    bl_options = {"DEFAULT_CLOSED"}

    @classmethod
    def poll(cls, context):
        return context.scene is not None and context.engine == "CYCLES"

    def draw_header(self, context):
        self.layout.prop(context.window_manager.neural_finishing, "enabled", text="")

    def draw(self, context):
        layout = self.layout
        settings = context.window_manager.neural_finishing
        layout.use_property_split = True
        layout.use_property_decorate = False
        column = layout.column()
        column.enabled = settings.enabled and not settings.running
        column.prop(settings, "mode")
        for name in ("intensity", "structure", "tone", "style", "package_directory", "output_directory"):
            column.prop(settings, name)
        column.operator("render.neural_finishing_probe", icon="CHECKMARK")
        column.operator("render.neural_finishing", icon="RENDER_STILL")
        if settings.running:
            layout.operator("render.neural_finishing_cancel", icon="CANCEL")
        layout.label(text=settings.status, icon="INFO")
        layout.label(text="Separate SDR result; original HDR retained")
        if settings.last_job:
            row = layout.row()
            row.enabled = not settings.running
            row.prop(settings, "last_job")
            row = layout.row()
            row.enabled = settings.enabled and not settings.running
            row.operator("render.neural_finishing_resume", icon="FILE_REFRESH")
            row = layout.row(align=True)
            row.operator("render.neural_finishing_view", text="Original").processed = False
            row.operator("render.neural_finishing_view", text="Processed").processed = True


classes = (RENDER_PT_neural_finishing,)
