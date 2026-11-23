-- Меню «Качество картинки»: реальное разрешение видео и фактическое состояние апскейла.
-- Состояние берётся из проходов рендера, а не из настроек: шейдер FSRCNNX сам отключается,
-- если картинку не нужно увеличивать.

local utils = require("mp.utils")
local options = { ready_file = "" }
require("mp.options").read_options(options, "cinema")

local MENU_TYPE = "cinema-picture"
local REFRESH_DELAY_SECONDS = 0.4
-- Имена проходов нейросетевых шейдеров: FSRCNNX и Anime4K.
local PASS_PATTERNS = { "feature map", "Anime4K" }

local saved_shaders = nil

local STATE_TEXT = {
    vsr = "Включён, RTX VSR",
    active = "Работает",
    not_needed = "Не требуется",
    disabled = "Выключен",
    unavailable = "Недоступен",
}

local function shader_list()
    return mp.get_property_native("glsl-shaders") or {}
end

local function has_missing_file(list)
    for _, path in ipairs(list) do
        local expanded = mp.command_native({ "expand-path", path })
        if not expanded or not utils.file_info(expanded) then
            return true
        end
    end
    return false
end

local function has_shader_passes()
    local passes = mp.get_property_native("vo-passes") or {}
    for _, group in ipairs({ passes.fresh or {}, passes.redraw or {} }) do
        for _, pass in ipairs(group) do
            for _, pattern in ipairs(PASS_PATTERNS) do
                if pass.desc and pass.desc:find(pattern, 1, true) then
                    return true
                end
            end
        end
    end
    return false
end

-- Фильтр RTX VSR с меткой @vsr. Драйвер не сообщает, применил ли он улучшение, поэтому
-- состояние показывает только, что VSR включён.
local function vsr_filter()
    for _, filter in ipairs(mp.get_property_native("vf") or {}) do
        if filter.label == "vsr" then
            return filter
        end
    end
    return nil
end

local function upscale_state()
    local vsr = vsr_filter()
    if vsr then
        return vsr.enabled == false and "disabled" or "vsr"
    end
    local list = shader_list()
    if #list == 0 then
        return "disabled"
    end
    if has_missing_file(list) then
        return "unavailable"
    end
    return has_shader_passes() and "active" or "not_needed"
end

local function video_size()
    local width = mp.get_property_number("width")
    local height = mp.get_property_number("height")
    if width and height then
        return string.format("%d×%d", width, height)
    end
    return "—"
end

local function menu_json()
    return utils.format_json({
        type = MENU_TYPE,
        title = "Качество картинки",
        keep_open = true,
        items = {
            { title = "Исходное видео", hint = video_size(), selectable = false },
            {
                title = "Апскейл",
                hint = STATE_TEXT[upscale_state()],
                value = { "script-message-to", mp.get_script_name(), "toggle-upscale" },
            },
        },
    })
end

local function refresh_menu()
    mp.commandv("script-message-to", "uosc", "update-menu", menu_json())
end

local function toggle_upscale()
    if vsr_filter() then
        mp.commandv("vf", "toggle", "@vsr")
        mp.add_timeout(REFRESH_DELAY_SECONDS, refresh_menu)
        return
    end
    local list = shader_list()
    if #list > 0 then
        saved_shaders = list
        mp.set_property_native("glsl-shaders", {})
    elseif saved_shaders then
        mp.set_property_native("glsl-shaders", saved_shaders)
    end
    -- Новые проходы появляются только после следующего кадра.
    mp.add_timeout(REFRESH_DELAY_SECONDS, refresh_menu)
end

-- Сообщаем лаунчеру, что фильм действительно пошёл: тогда он снимает экран «Открываем плеер».
local function report_ready()
    mp.unregister_event(report_ready)
    if options.ready_file ~= "" then
        local file = io.open(options.ready_file, "w")
        if file then
            file:write("ready")
            file:close()
        end
    end
end
mp.register_event("playback-restart", report_ready)

mp.register_script_message("toggle-upscale", toggle_upscale)
mp.register_script_message("picture-menu", function()
    mp.commandv("script-message-to", "uosc", "open-menu", menu_json())
end)
