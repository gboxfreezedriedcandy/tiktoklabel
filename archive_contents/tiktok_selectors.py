# Selector sets used throughout the flows.

# --- Left menu: Orders -> Manage orders ---
ORDERS_MENU_HEADER = [
    "div.core-menu-inline-header:has-text('Orders')",
    "//div[contains(@class,'core-menu-inline-header')][.//div[contains(@class,'pulse-menu-title-txt') and normalize-space()='Orders']]",
]

ORDERS_MANAGE_LINK = [
    "a[href$='/order']",
    "a[href*='/order?']",
    "//a[.//div[contains(@class,'pulse-menu-title-txt') and normalize-space()='Manage orders']]",
]

# --- Top/other navigation fallbacks ---
ORDERS_NAV_LINK = [
    "a[href*='/orders/to_ship']",
    "a[href*='/fulfillment/orders/to-ship']",
    "a[href*='/order/list?tab=to_ship']",
    "a[href$='/order']",
    "//a[normalize-space()='Orders']",
]

# --- Filter drawer ---
FILTER_TOGGLE = [
    "button[data-log_click_for='filter_button']",
    "//button[.//span[normalize-space()='Filter']]",
    "button.theme-m4b-button:has-text('Filter')",
]

DRAWER = [
    "div.theme-arco-drawer-content",
    "//div[contains(@class,'theme-arco-drawer-content')]",
]

DRAWER_APPLY = [
    "button[data-log_click_for='apply']",
    "//button[.//span[normalize-space()='Apply']]",
]

# --- Orders table ---
LOADING = [
    ".theme-arco-spin",
    ".arco-spin",
    "div[aria-busy='true']",
    "//div[contains(@class,'spin') or contains(@class,'loading')]",
]

TABLE_ROWS = [
    "div[data-tid='m4b_table']//div[contains(@class,'theme-arco-table-tr')]",
    "//div[@data-tid='m4b_table']//div[contains(@class,'table-tr')]",
]

ROW_CHECKBOXES = [
    "label[data-tid='m4b_checkbox'] input[type='checkbox']",
    "//label[@data-tid='m4b_checkbox']//input[@type='checkbox']",
]

# Pagination (orders table)
# We keep these broad to adapt to Arco/pulse variants and potential DOM shifts.
PAGINATION_CONTAINER = [
    ".theme-arco-pagination",
    ".arco-pagination",
    "//div[contains(@class,'pagination')][not(contains(@class,'simple'))]",
]
PAGINATION_SIZE_CHANGER = [
    ".theme-arco-pagination [class*='size-changer']",
    ".arco-pagination [class*='size-changer']",
    "//div[contains(@class,'pagination')]//div[contains(@class,'size-changer')]",
    # Fallback: any select-like element inside pagination (role/aria patterns)
    "//div[contains(@class,'pagination')]//*[@role='combobox']",
    "//div[contains(@class,'pagination')]//*[contains(@class,'select')]",
]

SELECT_ALL_HEADER = [
    "label[data-tid='m4b_checkbox'][data-id='fulfillment.table.select_current_package']",
    "//label[@data-id='fulfillment.table.select_current_package']",
    "(//label[@data-tid='m4b_checkbox'])[1]",
]

BULK_SELECT_ALL_BUTTON = [
    "button[data-id='fulfillment.table.select_all_package']",
    "button[data-log_click_for='bulk_select']",
    # Text variants that appear after ticking header checkbox
    "//button[.//span[contains(normalize-space(),'Select all') and contains(normalize-space(),'orders')]]",
    "//button[.//span[contains(normalize-space(),'Select the first') and contains(normalize-space(),'orders')]]",
    # Most specific attribute combo (defensive)
    "button[data-log_click_for='bulk_select'][data-id='fulfillment.table.select_all_package']",
]

BULK_RESET_BUTTON = [
    "button[data-tid='m4b_button'][data-log_click_for='deselect']",
    "button.theme-m4b-button[data-log_click_for='deselect']",
    "button[data-log_click_for='deselect']",
    "//button[normalize-space()='Reset']",
    "//button[.//span[normalize-space()='Reset']]",
]

SHIP_BULK_RESET_BUTTON = BULK_RESET_BUTTON + [
    "button[data-log_click_for='deselect_package']",
    "button[data-log_click_for='deselect_packages']",
    "button[data-tid='m4b_button'][data-log_click_for*='deselect_package']",
]

BULK_SELECT_ALL_LINK = [
    "//a[contains(translate(normalize-space(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'select all') and contains(translate(normalize-space(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'orders')]",
    "//span[contains(translate(normalize-space(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'select all') and contains(translate(normalize-space(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'orders')]",
]

ARRANGE_SHIPMENT_BUTTON = [
    "button[data-id='fulfillment.manage_order.batch_arrange_shipment']",
    "button[data-log_click_for='arrange_shipment']",
    "button[data-tid='m4b_button'][data-log_click_for='arrange_shipment']",
    "//div[@role='button'][.//span[contains(normalize-space(),'Arrange shipment')]]",
    "//span[contains(normalize-space(),'Arrange shipment')]/ancestor::button[1]",
    "//button[.//span[contains(normalize-space(),'Arrange shipment')]]",
]

# --- Shipping page ---
SHIP_LOADING = [
    ".theme-arco-spin",
    ".arco-spin",
    "div[aria-busy='true']",
    "//div[contains(@class,'spin') or contains(@class,'loading')]",
]

SHIP_SELECT_ALL_LABEL = [
    "label[data-tid='m4b_checkbox'][data-id='fulfillment.table.select_current_package']",
    "//label[@data-tid='m4b_checkbox' and @data-id='fulfillment.table.select_current_package']",
]

SHIP_BULK_SELECT_ALL = [
    "button[data-id='fulfillment.table.select_all_package']",
    "//button[.//span[contains(normalize-space(),'Select all') and contains(normalize-space(),'packages')]]",
]

SHIP_BULK_SELECT_ALL_LINK = [
    "//a[contains(translate(normalize-space(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'select all') and contains(translate(normalize-space(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'packages')]",
    "//span[contains(translate(normalize-space(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'select all') and contains(translate(normalize-space(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'packages')]",
]

SHIP_TABLE_ROWS = [
    "div[data-tid='m4b_table']//div[contains(@class,'theme-arco-table-tr')]",
    "//div[@data-tid='m4b_table']//div[contains(@class,'table-tr')]",
]

SHIP_ROW_CHECKED = [
    "label.core-checkbox-checked",
    "//label[contains(@class,'core-checkbox-checked')]",
]

SHIP_ROW_CHECKBOXES = [
    "label[data-tid='m4b_checkbox'] input[type='checkbox']",
    "//label[@data-tid='m4b_checkbox']//input[@type='checkbox']",
]

EDIT_WEIGHT_BUTTON = [
    "button[data-id='fulfillment.manage_order.batch_edit_weight_all_package_info']",
    "//button[.//span[normalize-space()='Edit weight']]",
]

WEIGHT_INPUT = [
    "input#packageWeight_input",
    "input[data-id='fulfillment.create_shipping_label.input.package_weight']",
    "//label[@for='packageWeight']/following::input[1]",
]

SINGLE_WEIGHT_INPUT = [
    "input#packageWeight_input",
    "input[data-id='fulfillment.create_shipping_label.input.package_weight']",
    "//label[@for='packageWeight']/following::input[1]",
]

BATCH_EDIT_APPLY = [
    "button[data-log_click_for='bulk_edit_weight_amending_apply']",
    "//button[.//span[normalize-space()='Apply']]",
    "button[data-log_click_for='apply']",
]

ARRANGE_PRINT_BUTTON = [
    "button[data-id='fulfillment.create_shipping_label.buy_and_print_label']",
    "//button[.//span[contains(normalize-space(),'Arrange shipment') and contains(normalize-space(),'print')]]",
]

# --- Combine Orders modal ---
COMBINE_CONFIRM_BUTTON = [
    "button[data-id='fulfillment.combine_package.confirm_all_combination']",
    "button[data-log_click_for='accept_all_combination']",
    "//button[.//span[normalize-space()='Combine orders and continue']]",
]


# Breadcrumb "Manage Orders" (Arrange shipment page)
BACK_TO_MANAGE_ORDERS = [
    "a[data-log_click_for='back_to_order_list']",
    "a[data-tid='m4b_breadcrumb_link']",
    "//a[@data-log_click_for='back_to_order_list']",
    "[data-tid='m4b_breadcrumb'] [data-log_click_for='back_to_order_list']",
    "//div[@data-tid='m4b_breadcrumb']//span[@data-log_click_for='back_to_order_list']",
    "//div[contains(@class,'theme-arco-breadcrumb')]//span[@data-log_click_for='back_to_order_list']",
    "//div[@data-tid='m4b_breadcrumb']//span[contains(normalize-space(),'Manage Orders')]",
    # Most precise: within breadcrumb container, by tracking id
    "[data-tid='m4b_breadcrumb'] [data-log_click_for='back_to_order_list']",

    # XPath equivalents
    "//div[@data-tid='m4b_breadcrumb']//span[@data-log_click_for='back_to_order_list']",
    "//div[@role='list' and @data-tid='m4b_breadcrumb']//div[@role='listitem']//span[@data-log_click_for='back_to_order_list']",

    # Class-anchored fallbacks (in case data-tid changes but classes remain)
    "//div[contains(@class,'theme-arco-breadcrumb')]//span[@data-log_click_for='back_to_order_list']",
    "div.theme-arco-breadcrumb span[data-log_click_for='back_to_order_list']",

    # Text fallback (least preferred; localization-sensitive)
    "//div[@data-tid='m4b_breadcrumb']//span[contains(normalize-space(),'Manage Orders')]",
]

# Manage Orders page header title
MANAGE_ORDERS_HEADER = [
    "[data-tid='m4b_page_header'] .theme-m4b-page-header-title-text",
    "[data-tid='m4b_page_header'] .theme-m4b-page-header-title",
    "div.theme-m4b-page-header-title-text",
    "//div[@data-tid='m4b_page_header']//div[contains(@class,'page-header-title-text')]",
    "//div[contains(@class,'theme-m4b-page-header-title-text') and contains(normalize-space(),'Manage Orders')]",
]
