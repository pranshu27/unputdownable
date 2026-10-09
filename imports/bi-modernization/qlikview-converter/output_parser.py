from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, ConfigDict
from langchain_core.output_parsers import JsonOutputParser

class CommonDataSource(BaseModel):
    id: Optional[str] = Field(None, description="Stable identifier for the data source")
    name: Optional[str] = Field(None, description="Display name of the data source")
    source_type: Optional[str] = Field(None, description="Source type such as csv, excel, sql, or api")
    connection_mode: Optional[str] = Field(None, description="Connection mode such as import, extract, or directquery")
    authentication_method: Optional[str] = Field(None, description="Authentication method used by the source")
    server: Optional[str] = Field(None, description="Server name or host if present")
    database: Optional[str] = Field(None, description="Database name if present")
    schema_name: Optional[str] = Field(None, alias="schema", description="Schema name if present")
    path: Optional[str] = Field(None, description="Primary file path or connection path if present")
    paths: Optional[List[str]] = Field(None, description="All file/table paths when datasource uses multiple source files (e.g. multi-table CSV datasources)")
    gateway: Optional[str] = Field(None, description="Gateway or bridge name if present")
    refresh_frequency: Optional[str] = Field(None, description="Refresh schedule or frequency if present")

    model_config = ConfigDict(populate_by_name=True)


class CommonColumnVariation(BaseModel):
    name: Optional[str] = Field(None, description="Variation name as declared in the model (typically 'Variation' for Power BI auto date)")
    is_default: bool = Field(False, description="Whether this is the default variation for the column")
    relationship_id: Optional[str] = Field(None, description="ID of the relationship that links this column to the variation table")
    default_hierarchy: Optional[str] = Field(None, description="Fully-qualified default hierarchy on the variation table, e.g. 'LocalDateTable_xxx.Date Hierarchy'")


class CommonTableColumn(BaseModel):
    name: Optional[str] = Field(None, description="Column name")
    data_type: Optional[str] = Field(None, description="Data type")
    nullable: bool = Field(False, description="Whether the column can be null")
    hidden: bool = Field(False, description="Whether the column is hidden")
    semantic_role: Optional[str] = Field(None, description="Semantic role such as dimension, measure, or key")
    used_in_relationships: bool = Field(False, description="Whether the column participates in relationships")
    used_in_filters: bool = Field(False, description="Whether the column is used in filters")
    used_in_groupby: bool = Field(False, description="Whether the column is used in group by operations")
    used_in_calculations: bool = Field(False, description="Whether the column is used in calculations")
    distinct_count_high: bool = Field(False, description="Whether the column has high cardinality")
    description: Optional[str] = Field(None, description="Human readable description")
    variations: List[CommonColumnVariation] = Field(default_factory=list, description="Variations on this column. Power BI auto-date columns reference a LocalDateTable's Date Hierarchy via a variation named 'Variation'.")
    expression: Optional[str] = Field(None, description="DAX expression body if this column is calculated. Empty/None for physical source columns. Calc-column lineage lives here so the column itself carries its formula, not a separate calculations[] entry.")
    sort_by_column: Optional[str] = Field(None, description="If sorting on this column should use a different column's values, that column's name (e.g. Month sorted by MonthNo).")
    format_string: Optional[str] = Field(None, description="Display format string for the column (e.g. 'dd-mm-yyyy', '0.00'). Mirrors the TMDL 'formatString' attribute.")
    parameter_metadata: Optional[Dict[str, Any]] = Field(None, description="When the parent table is a Power BI Field Parameter, this carries the column's ParameterMetadata extended property ({'version': 3, 'kind': 2} on the Fields column).")


class CommonIngestionStep(BaseModel):
    order: int = Field(..., description="Step order")
    step_type: str = Field(..., description="Type of ingestion step")
    description: str = Field(..., description="Human readable description of the step")
    native_expressions: Dict[str, str] = Field(
        default_factory=dict,
        description="Tool-native expressions for this step, keyed by tool name"
    )

    model_config = ConfigDict(extra="allow")


class CommonIngestion(BaseModel):
    steps: List[CommonIngestionStep] = Field(..., description="Ordered ingestion steps")


class CommonHierarchyLevel(BaseModel):
    name: Optional[str] = Field(None, description="Level name (e.g., Year, Quarter, Month, Day)")
    column: Optional[str] = Field(None, description="Column on this table that the level references")
    ordinal: Optional[int] = Field(None, description="Ordinal position within the hierarchy (0-based)")


class CommonHierarchy(BaseModel):
    name: Optional[str] = Field(None, description="Hierarchy name as declared in the model, e.g. 'Date Hierarchy'")
    levels: List[CommonHierarchyLevel] = Field(default_factory=list, description="Ordered levels in the hierarchy")


class CommonTable(BaseModel):
    id: Optional[str] = Field(None, description="Stable identifier for the table")
    name: Optional[str] = Field(None, description="Display name of the table")
    table_type: Optional[str] = Field(None, description="Table type such as dimension, fact, bridge, or lookup")
    source_data_source_id: Optional[str] = Field(None, description="Related data source identifier if any")
    source_derived_from_table_id: Optional[str] = Field(None, description="Source table identifier if derived")
    is_materialized: bool = Field(False, description="Whether the table is materialized")
    hidden: bool = Field(False, description="Whether the table is hidden in the model. Power BI auto-date tables (LocalDateTable_*/DateTableTemplate_*) are hidden + showAsVariationsOnly.")
    description: Optional[str] = Field(None, description="Table description")
    columns: List[CommonTableColumn] = Field(default_factory=list, description="Columns included in the table")
    hierarchies: List[CommonHierarchy] = Field(default_factory=list, description="Hierarchies declared on the table. Power BI auto date tables carry a standard 'Date Hierarchy' with Year/Quarter/Month/Day.")
    ingestion: CommonIngestion = Field(default_factory=lambda: CommonIngestion(steps=[]), description="Ingestion / transformation steps")


class CommonRelationship(BaseModel):
    id: Optional[str] = Field(None, description="Stable identifier for the relationship")
    left_table_id: Optional[str] = Field(None, description="Left table identifier")
    left_column: Optional[str] = Field(None, description="Left column name")
    right_table_id: Optional[str] = Field(None, description="Right table identifier")
    right_column: Optional[str] = Field(None, description="Right column name")
    cardinality: Optional[str] = Field(None, description="Relationship cardinality")
    join_type: Optional[str] = Field(None, description="Join type")
    active: bool = Field(False, description="Whether the relationship is active")
    filter_direction: Optional[str] = Field(None, description="Filter direction")
    enforced_integrity: bool = Field(False, description="Whether referential integrity is enforced")
    relationship_type: Optional[str] = Field(None, description="Relationship type")
    note: Optional[str] = Field(None, description="Optional migration note")


class CommonCalculationDisplay(BaseModel):
    folder: Optional[str] = Field(None, description="Display folder")
    hidden: bool = Field(False, description="Whether the calculation is hidden")
    tags: Optional[List[str]] = Field(None, description="Tags used for organization")


class CommonCalculationExpressions(BaseModel):
    tableau: Optional[str] = Field(None, description="Raw Tableau formula")
    dax: Optional[str] = Field(None, description="DAX expression for Power BI")
    qlik: Optional[str] = Field(None, description="Qlik expression")


class ParameterConfig(BaseModel):
    """Configuration for parameter calculations (min/max/step/current/control)."""
    current_value: Optional[Any] = Field(None, description="Current/default value of the parameter")
    min_value: Optional[Any] = Field(None, description="Minimum allowed value")
    max_value: Optional[Any] = Field(None, description="Maximum allowed value")
    step_size: Optional[Any] = Field(None, description="Step/increment size")
    allowed_values: Optional[List[Any]] = Field(None, description="List of allowed discrete values (if not range-based)")
    control_type: Optional[str] = Field(None, description="UI control type: slider, dropdown, type-in, radio")


class CommonCalculation(BaseModel):
    id: Optional[str] = Field(None, description="Stable identifier for the calculation")
    name: Optional[str] = Field(None, description="Calculation name")
    home_table: Optional[str] = Field(None, description="Table that owns this measure in the model — TMDL emits the measure inside this table's block. Source-of-truth: dax_measures.json TableName. Independent of depends_on_columns (e.g. TotalRevenue lives on CustomerCountPerDay but depends on Revenue Daywise.Revenue).")
    description: Optional[str] = Field(None, description="Human readable description")
    semantic_type: Optional[str] = Field(None, description="Semantic type such as sum, ratio, or growth_rate")
    aggregation_behavior: Optional[str] = Field(None, description="Aggregation behavior such as additive or non_additive")
    data_type: Optional[str] = Field(None, description="Output data type")
    format_string: Optional[str] = Field(None, description="Display format string")
    is_base_measure: bool = Field(False, description="Whether this is a base measure")
    reusable: bool = Field(False, description="Whether the calculation is reusable")
    depends_on_columns: Optional[List[str]] = Field(None, description="Base table columns referenced by the calculation in Table.Column format (e.g. 'df_OrderItems.price')")
    depends_on_measures: Optional[List[str]] = Field(None, description="Other calculation or measure names referenced by the calculation")
    display: Optional[CommonCalculationDisplay] = Field(None, description="Display metadata")
    expressions: Optional[CommonCalculationExpressions] = Field(None, description="Tool-specific expressions")
    # Parameter-specific fields (populated only when semantic_type="parameter")
    parameter_config: Optional["ParameterConfig"] = Field(None, description="Parameter configuration (min, max, step, current value, control type). Only populated for parameters.")


class CommonModelOutput(BaseModel):
    data_sources: List[CommonDataSource] = Field(..., description="List of workbook data sources")
    tables: List[CommonTable] = Field(..., description="List of tables and transformation lineage")
    relationships: List[CommonRelationship] = Field(..., description="List of relationships between tables")
    calculations: List[CommonCalculation] = Field(..., description="List of measures and calculations")
    # NOTE: visualizations is NOT part of this schema. It is injected at runtime by the
    # VisualsLayoutAgent in sequentialworkflow.py via final_parsed["visualizations"].
    # Keeping it out of CommonModelOutput avoids Pydantic v1 forward-reference issues
    # and keeps the model extraction agent's output schema clean.

    model_config = ConfigDict(extra="ignore")


workbook_parser = JsonOutputParser(pydantic_object=CommonModelOutput)

#output parsers for qlikview:

class DataField(BaseModel):
    name: str = Field(..., description="Name of the field")
    type: str = Field(..., description="Data type of the field")

class DataModelTable(BaseModel):
    table_name: str = Field(..., description="Name of the table in the data model")
    tool: str = Field(..., description="Tool from which the data model is extracted")
    fields: List[DataField] = Field(..., description="List of fields in the table")
    relationships: List[str] = Field(..., description="List of relationship definitions with other tables")
    used_by: List[str] = Field(..., description="List of objects or components that use this table")

class DataSource(BaseModel):
    name: str = Field(..., description="Name of the data source")
    tool: str = Field(..., description="Tool used to connect to the data source")
    type: str = Field(..., description="Type of the data source (e.g., SQL, Excel, Web API)")
    connection_details: str = Field(..., description="Details about the connection string or method")
    authentication_method: str = Field(..., description="Method of authentication used for the source")
    refresh_schedule: str = Field(..., description="Schedule on which the source is refreshed")
    used_by: List[str] = Field(..., description="List of objects or components using this source")
    is_extract: bool = Field(..., description="Whether the data source is an extract")
    extract_refresh_schedule: str = Field(..., description="Refresh schedule if the source is an extract")
    is_published: bool = Field(..., description="Whether the source is published/shared")

class DataTransformation(BaseModel):
    name: str = Field(..., description="Name of the transformation like country, city")
    tool: str = Field(..., description="Tool used to create the transformation")
    data_type: str = Field(..., description="Data type of the transformation result")
    role: str = ""
    expression: str = Field(..., description="Expression or formula used in the transformation")
    description: str = Field(..., description="Description of what the transformation does")
    used_in: List[str] = Field(..., description="List of components using this transformation")
    filters: List[str] = Field(..., description="Filters applied to this transformation")

class QlikDataCore(BaseModel):
    data_sources: List[DataSource] = Field(..., description="List of data sources used")
    data_model: List[DataModelTable] = Field(..., description="List of tables in the data model")
    data_transformations: List[DataTransformation] = Field(..., description="List of data transformations")

qlik_data_core_output_parser = JsonOutputParser(pydantic_object=QlikDataCore)



class Hierarchy(BaseModel):
    name: str = Field(..., description="Name of the hierarchy/ group")
    members: List[str] = Field(..., description="Ordered list of hierarchy levels/ group levels")

class HierarchyWrapper(BaseModel):
    hierarchies: List[Hierarchy] = Field(..., description="List of hierarchies/ groups")

hierarchy_output_parser = JsonOutputParser(pydantic_object=HierarchyWrapper)



class VisualizationFormatting(BaseModel):
    font: str = Field(..., description="Font used for labels/text")
    font_size: int = Field(..., description="Font size used for main content")
    caption_font: str = Field(..., description="Font used for captions")
    caption_font_size: int = Field(..., description="Font size for captions")

class ChartMappings(BaseModel):
    x_axis: Optional[str] = Field(None, description="Field used for the X-axis in the scatter chart")
    y_axis: Optional[str] = Field(None, description="Field used for the Y-axis in the scatter chart")
    secondary_y_axis: Optional[str] = Field(None, description="Field that determines the size of the data points")
    size: Optional[str] = Field(None, description="Field that determines the size of the data points")
    legend: Optional[str] = Field(None, description="Field used for the legend grouping")
    details: Optional[str] = Field(None, description="Field used for the legend grouping same as legend")

class StraightTableColumn(BaseModel):
    name: str = Field(..., description="Name of the column (dimension or measure)")
    expression: str = Field(..., description="Expression/formula for the column")

class Visualization(BaseModel):
    object_id: str = Field(..., description="Unique Object ID of the visualization (e.g., CH01, TB02)")
    name: str = Field(..., description="User-facing name/title of the visualization")
    type: str = Field(..., description="Type of the visualization (e.g., Combo Chart, Pie chart, Scatter Chart, Straight Table, Bar Chart)")
    dimensions: Optional[List[str]] = Field(default_factory=list, description="List of dimension fields used in the visualization")
    measures: Optional[List[str]] = Field(default_factory=list, description="List of measure fields used in the visualization")
    filters: List[str] = Field(..., description="List of filters applied to the visualization")
    chart_mappings: Optional[ChartMappings] = Field(None, description="Mappings for chart axes if the visualization is a scatter chart")
    straight_table_columns: Optional[List[StraightTableColumn]] = Field(None, description="List of columns if the visualization is a straight table")
    formatting: VisualizationFormatting = Field(..., description="Formatting settings of the visualization")

class VisualizationList(BaseModel):
    Visualizations: List[Visualization] = Field(..., description="List of extracted visualizations with all details")

visualization_output_parser = JsonOutputParser(pydantic_object=VisualizationList)


class FilterFormatting(BaseModel):
    font: str = Field(..., description="Font used for the filter")
    size: str = Field(..., description="Font size used for the filter")
    bold: bool = Field(..., description="Whether the filter text is bold")
    italic: bool = Field(..., description="Whether the filter text is italic")
    underline: bool = Field(..., description="Whether the filter text is underlined")

class Filter(BaseModel):
    object_id: str = Field(..., description="Unique ID of the filter object")
    name: str = Field(..., description="Display name of the filter")
    type: str = Field(..., description="Type of the filter (e.g., listbox, dropdown)")
    columns: List[str] = Field(..., description="Columns associated with the filter")
    formatting: FilterFormatting = Field(..., description="Formatting settings for the filter")
    background_color: Optional[str] = Field(None, description="Background color of the filter")

class FilterWrapper(BaseModel):
    filters: List[Filter] = Field(..., description="List of filters extracted")

filter_output_parser = JsonOutputParser(pydantic_object=FilterWrapper)



class ParameterVariable(BaseModel):
    name: str = Field(..., description="Name of the parameter or variable")
    type: str = Field(..., description="Type (parameter or variable)")
    calculation: str = Field(..., description="Expression or calculation logic")

class ParameterVariableWrapper(BaseModel):
    parameters_variables: List[ParameterVariable] = Field(..., description="List of parameters and variables extracted")

parameter_variable_output_parser = JsonOutputParser(pydantic_object=ParameterVariableWrapper)



class Sheet(BaseModel):
    object_id: str = Field(..., description="Unique ID of the sheet object")
    name: str = Field(..., description="Display name of the sheet")

class SheetWrapper(BaseModel):
    sheets: List[Sheet] = Field(..., description="List of sheets or report pages")

sheet_output_parser = JsonOutputParser(pydantic_object=SheetWrapper)



class DashboardPosition(BaseModel):
    x: Optional[int] = Field(None, description="X-coordinate of the component")
    y: Optional[int] = Field(None, description="Y-coordinate of the component")
    height: Optional[int] = Field(None, description="Height of the component")
    width: Optional[int] = Field(None, description="Width of the component")

class DashboardComponent(BaseModel):
    name: str = Field(..., description="Name of the dashboard component")
    object_id: str = Field(..., description="Unique ID of the component")
    position: DashboardPosition = Field(..., description="Positioning and size of the component")
    font_size: Optional[int] = Field(None, description="Font size used in the component")
    color: Optional[str] = Field(None, description="Color used in the component")

class Dashboard(BaseModel):
    name: str = Field(..., description="Name of the dashboard")
    object_id: str = Field(..., description="Unique ID of the dashboard")
    height: int = Field(..., description="Height of the dashboard")
    width: int = Field(..., description="Width of the dashboard")
    background_color: Optional[str] = Field(None, description="Background color of the dashboard")
    components: List[DashboardComponent] = Field(..., description="List of components placed in the dashboard")

class DashboardWrapper(BaseModel):
    dashboards: List[Dashboard] = Field(..., description="List of dashboards extracted")

dashboard_output_parser = JsonOutputParser(pydantic_object=DashboardWrapper)


# =============================================================================
# COMMON VISUAL MODEL OUTPUT SCHEMA
# Tool-agnostic visual model that captures visualizations from Tableau, Power BI,
# QlikView, or any BI tool into a single migratable format.
# Follows the Power BI input.json pattern: flat pages → visuals → fields.
# Populated by the VisualsLayoutAgent in sequentialworkflow.py.
# =============================================================================


class VisualPosition(BaseModel):
    """Position and size of a visual on the page canvas, in pixels."""
    x: float = Field(0, description="X coordinate in pixels")
    y: float = Field(0, description="Y coordinate in pixels")
    width: float = Field(0, description="Width in pixels")
    height: float = Field(0, description="Height in pixels")
    z_order: Optional[int] = Field(None, description="Stacking order (higher = on top). Derived from zone order for Tableau, explicit for Power BI.")


class VisualFieldBinding(BaseModel):
    """A single data binding — maps a field to a visual role."""
    role: Optional[str] = Field(None, description="Normalized role: Category, Y, Y2, Series, Values, Group, Size, Color, Shape, Label, Detail, Tooltip, Filter, Pages")
    table: Optional[str] = Field(None, description="Source table name")
    column: Optional[str] = Field(None, description="Source column name")
    aggregation: Optional[str] = Field(None, description="Aggregation: Sum, Count, CountNonNull, CountDistinct, Average, Min, Max, Median, or empty string for none")
    query_ref: Optional[str] = Field(None, description="Raw native expression (Tableau shelf ref / PBI query_ref)")


# NOTE: Colors / fonts / borders / page palettes are NOT produced by the LLM.
# They are extracted deterministically from the source files by style_extractor.py
# and merged post-flow as the top-level `theme` and per-visual `style` objects.
# (Former TextStyleConfig / ZoneStyleConfig / StylePreference / ColorPalette models
# were removed when that styling moved off the LLM.)


class TooltipConfig(BaseModel):
    """Custom tooltip content shown on hover."""
    formatted_text: Optional[str] = Field(None, description="Full tooltip text content")
    field_references: List[str] = Field(default_factory=list, description="Field names embedded in the tooltip")


class MarkLabelConfig(BaseModel):
    """Data label visibility and formatting."""
    show_data_labels: bool = Field(False, description="Whether data labels are shown")
    formatting: Dict[str, str] = Field(default_factory=dict, description="Label formatting attributes")


class SortConfig(BaseModel):
    """Sort definition applied to a field."""
    column: Optional[str] = Field(None, description="Column being sorted")
    direction: Optional[str] = Field(None, description="Sort direction: ASC or DESC")


class AxisConfig(BaseModel):
    """Configuration for a chart axis."""
    field: Optional[str] = Field(None, description="Field or ordinal the axis represents")
    title: Optional[str] = Field(None, description="Custom axis title text")
    range_min: Optional[str] = Field(None, description="Custom minimum axis value")
    range_max: Optional[str] = Field(None, description="Custom maximum axis value")
    reversed: bool = Field(False, description="Whether the axis direction is reversed")
    logarithmic: bool = Field(False, description="Whether logarithmic scale is enabled")
    tick_formatting: Dict[str, str] = Field(default_factory=dict, description="Tick mark format attributes")


class LegendConfig(BaseModel):
    """Legend definition for color, size, or shape encodings."""
    encoding_type: Optional[str] = Field(None, description="Encoding type: color, size, shape, or label")
    field: Optional[str] = Field(None, description="Field driving the legend")
    title: Optional[str] = Field(None, description="Legend title text")
    position: Optional[str] = Field(None, description="Legend position: right, left, top, bottom")
    visible: bool = Field(True, description="Whether the legend is visible")


class ReferenceLineConfig(BaseModel):
    """Reference line, band, or distribution overlay on a chart."""
    reference_type: Optional[str] = Field(None, description="Type: line, band, or distribution")
    axis_or_field: Optional[str] = Field(None, description="Axis or field the reference is attached to")
    value: Optional[str] = Field(None, description="Constant value or computation: average, median, sum, etc.")
    label: Optional[str] = Field(None, description="Label text displayed on the reference line")
    formatting: Dict[str, str] = Field(default_factory=dict, description="Line style, color, thickness attributes")


class TrendLineConfig(BaseModel):
    """Trend line or forecast overlay on a chart."""
    trend_type: Optional[str] = Field(None, description="Type: trend or forecast")
    model_type: Optional[str] = Field(None, description="Model: linear, logarithmic, exponential, polynomial, power")
    fields: List[str] = Field(default_factory=list, description="Fields the trend line applies to")
    confidence_bands: bool = Field(False, description="Whether confidence bands are shown")
    forecast_periods: Optional[str] = Field(None, description="Number of periods to forecast forward")
    forecast_granularity: Optional[str] = Field(None, description="Granularity: year, quarter, month, week, day")


class DualAxisConfig(BaseModel):
    """Dual-axis configuration when two measures share a chart."""
    primary_field: Optional[str] = Field(None, description="Field on the primary (left/bottom) axis")
    secondary_field: Optional[str] = Field(None, description="Field on the secondary (right/top) axis")
    primary_axis_title: Optional[str] = Field(None, description="Custom title for the primary axis")
    secondary_axis_title: Optional[str] = Field(None, description="Custom title for the secondary axis")
    axes_synchronized: bool = Field(False, description="Whether the two axes share the same scale")


class ConditionalFormattingRule(BaseModel):
    """Color-based conditional formatting rule."""
    field: Optional[str] = Field(None, description="Field driving the color encoding")
    encoding_type: Optional[str] = Field(None, description="Encoding type: stepped, continuous, diverging, categorical")
    palette_name: Optional[str] = Field(None, description="Color palette name")
    color_steps: Optional[int] = Field(None, description="Number of color steps")
    min_value: Optional[str] = Field(None, description="Minimum value for the color range")
    max_value: Optional[str] = Field(None, description="Maximum value for the color range")
    mid_value: Optional[str] = Field(None, description="Mid-point value for diverging palettes")
    reversed: bool = Field(False, description="Whether the color scale is reversed")
    color_assignments: Optional[Dict[str, str]] = Field(None, description="Explicit color-to-value mapping for categorical fields (dimension value → hex color)")


class AnnotationConfig(BaseModel):
    """User-placed annotation on the chart canvas."""
    annotation_type: Optional[str] = Field(None, description="Annotation type: point, mark, or area")
    text: Optional[str] = Field(None, description="Annotation text content")
    position: Dict[str, str] = Field(default_factory=dict, description="x, y coordinates of the annotation")


class TableCalcConfig(BaseModel):
    """Table calculation addressing and partitioning definition (Tableau-specific)."""
    field_name: Optional[str] = Field(None, description="Table calculation field name")
    formula: Optional[str] = Field(None, description="Raw Tableau table calculation formula")
    calc_type: Optional[str] = Field(None, description="Calculation type: running_total, rank, lookup, window_aggregate, etc.")
    addressing_fields: List[str] = Field(default_factory=list, description="Fields the calc computes ACROSS")
    partitioning_fields: List[str] = Field(default_factory=list, description="Fields the calc restarts FOR")
    addressing_type: Optional[str] = Field(None, description="Addressing scope: table_down, table_across, pane_down, specific")


class InteractivityConfig(BaseModel):
    """Navigation and action button configuration."""
    navigation_target: Optional[str] = Field(None, description="Page ID to navigate to when clicked")
    button_type: Optional[str] = Field(None, description="Button type: back, bookmark, navigation")
    has_border: Optional[bool] = Field(None, description="Whether the visual has a border")


class CommonVisual(BaseModel):
    """A single visual on a page — data chart, textbox, image, slicer, or action button."""
    # --- Core identity ---
    visual_id: Optional[str] = Field(None, description="Unique visual identifier")
    visual_type: Optional[str] = Field(None, description="Normalized visual type. Chart types: bar_chart, stacked_bar_chart, line_chart, area_chart, pie_chart, scatter_plot, bubble_chart, dual_axis_chart, box_whisker_chart, map, heat_map, highlight_table, text_table, histogram, tree_map, kpi_card, gantt_chart, square, table. Non-chart types: textbox, image, slicer, paramctrl, container, navigation, webview, spacer, empty. Never use 'blank'.")
    title: Optional[str] = Field(None, description="Display title of the visual")
    source_tool: Optional[str] = Field(None, description="Originating tool: tableau, powerbi, qlikview")

    # --- Position ---
    position: Optional[VisualPosition] = Field(None, description="Position and size on the page canvas")

    # --- Data bindings ---
    fields: List[VisualFieldBinding] = Field(default_factory=list, description="Data bindings: role, table, column, aggregation, query_ref")
    datasource_dependencies: Optional[List[str]] = Field(None, description="Datasource names this visual reads from")

    # --- Textbox-specific ---
    content: Optional[str] = Field(None, description="Text content for textbox visuals")
    # Font styling for textboxes lives on the deterministic `style.title` (see style_extractor.py).

    # --- Image-specific ---
    imageUrl: Optional[str] = Field(None, description="Image URL or filename for image visuals")
    imageId: Optional[str] = Field(None, description="UUID reference to image stored in Postgres report_images table")

    # --- Navigation / action button ---
    navigation_target: Optional[str] = Field(None, description="Page ID to navigate to when clicked")
    button_type: Optional[str] = Field(None, description="Button type: back, bookmark, navigation")
    has_border: Optional[bool] = Field(None, description="Whether the visual has a border")
    # Container background / border / padding live on the deterministic
    # `style.container` (see style_extractor.py), not on the LLM output.

    # --- Tableau-rich visual properties (null for Power BI) ---
    mark_type: Optional[str] = Field(None, description="Tableau mark class: Automatic, Bar, Line, Circle, Text, Map, Pie, etc.")
    axes: Optional[List[AxisConfig]] = Field(None, description="Axis configurations")
    legends: Optional[List[LegendConfig]] = Field(None, description="Legend configurations")
    tooltip_config: Optional[TooltipConfig] = Field(None, description="Custom tooltip configuration")
    data_labels: Optional[MarkLabelConfig] = Field(None, description="Data label settings")
    sort_config: Optional[List[SortConfig]] = Field(None, description="Sort definitions")
    reference_lines: Optional[List[ReferenceLineConfig]] = Field(None, description="Reference lines/bands")
    trend_lines: Optional[List[TrendLineConfig]] = Field(None, description="Trend/forecast lines")
    dual_axis: Optional[DualAxisConfig] = Field(None, description="Dual-axis configuration")
    conditional_formatting: Optional[List[ConditionalFormattingRule]] = Field(None, description="Color encoding rules")
    annotations: Optional[List[AnnotationConfig]] = Field(None, description="Chart annotations")
    table_calc_configs: Optional[List[TableCalcConfig]] = Field(None, description="Table calculation definitions")


class CommonReportPage(BaseModel):
    """A single page/dashboard in the common visual model."""
    page_id: Optional[str] = Field(None, description="Unique page identifier (dashboard UUID / PBI page_id)")
    display_name: Optional[str] = Field(None, description="Human-readable page name")
    width: Optional[float] = Field(None, description="Canvas width in pixels")
    height: Optional[float] = Field(None, description="Canvas height in pixels")
    visuals: List[CommonVisual] = Field(default_factory=list, description="All visuals on this page")
    # `styles` (page background / filter pane) and `color_palettes` are filled
    # deterministically post-flow by style_extractor.py, not by the LLM.
    actions: Optional[List[Dict[str, Any]]] = Field(None, description="Dashboard interactivity actions (filter, highlight, URL, navigation) triggered by user interaction on visuals")


class CommonVisualsOutput(BaseModel):
    """Top-level output for the visual section of the common model.
    Replaces the old VisualsOutput (worksheets + dashboards + presentation)."""
    pages: List[CommonReportPage] = Field(
        default_factory=list,
        description="All pages/dashboards with their visuals"
    )


visuals_parser = JsonOutputParser(pydantic_object=CommonVisualsOutput)
