// The hidden select remains the editor's data source; the popup owns interaction.
(() => {
  const select = document.getElementById('skill-category-select');
  const trigger = document.getElementById('skill-category-trigger');
  const label = document.getElementById('skill-category-current');
  if (!select || !trigger) return;
  const text = (zh, en) => currentLanguage === 'zh' ? zh : en;
  let popup = null, search = null, list = null, active = 0, matches = [], returnFocus = true;

  function sync() {
    label.textContent = select.selectedOptions[0]?.textContent || text('未分类', 'Uncategorized');
    trigger.disabled = select.disabled;
    trigger.title = label.textContent;
    if(typeof updateSkillCategoryDeleteButton==='function')updateSkillCategoryDeleteButton();
    if (popup && (select.disabled || !document.getElementById('editor-modal').classList.contains('active'))) close(false);
    else if (popup) render();
  }
  function close(focus = returnFocus) {
    if (!popup) return;
    popup.remove(); popup = search = list = null;
    trigger.setAttribute('aria-expanded', 'false');
    if (focus && !trigger.disabled) trigger.focus();
  }
  window.closeSkillCategoryPicker = close;
  function position() {
    if (!popup) return;
    const rect = trigger.getBoundingClientRect();
    const width = Math.min(360, Math.max(240, rect.width), window.innerWidth - 24);
    popup.style.width = `${width}px`;
    popup.style.left = `${Math.max(12, Math.min(rect.left, window.innerWidth - width - 12))}px`;
    const height = Math.min(310, popup.scrollHeight);
    const below = window.innerHeight - rect.bottom - 14;
    const above = rect.top - 14;
    const upward = below < height && above > below;
    const available = Math.max(100, upward ? above : below);
    popup.style.maxHeight = `${Math.min(310, available)}px`;
    popup.style.top = `${upward ? Math.max(12, rect.top - Math.min(height, available) - 6) : rect.bottom + 6}px`;
  }
  function choose(option) {
    select.value = option.value;
    select.dispatchEvent(new Event('change', {bubbles: true}));
    sync(); close();
  }
  function activate(index) {
    active = Math.max(0, Math.min(index, matches.length - 1));
    const buttons = [...list.querySelectorAll('[role="option"]')];
    buttons.forEach((button, i) => button.classList.toggle('keyboard-active', i === active));
    const button = buttons[active];
    if (button) {search.setAttribute('aria-activedescendant', button.id); button.scrollIntoView({block:'nearest'});}
    else search.removeAttribute('aria-activedescendant');
  }
  function render() {
    const query = search.value.trim().toLocaleLowerCase();
    matches = [...select.options].filter(o => !o.disabled && o.textContent.toLocaleLowerCase().includes(query));
    list.replaceChildren();
    if (!matches.length) {
      const empty = document.createElement('div'); empty.className = 'category-picker-empty';
      empty.textContent = text('没有匹配分类，可使用“新增类别”添加', 'No matching category. Use Add category.'); list.append(empty);
    }
    for (const [index, option] of matches.entries()) {
      const button = document.createElement('button'); button.type = 'button'; button.id = `category-option-${index}`;
      button.className = 'category-picker-option'; button.setAttribute('role', 'option'); button.tabIndex = -1;
      button.setAttribute('aria-selected', String(option.value === select.value));
      const name = document.createElement('span'); name.textContent = option.textContent;
      const check = document.createElement('span'); check.className = 'category-picker-check'; check.textContent = option.value === select.value ? '✓' : '';
      button.append(name, check); button.onclick = () => choose(option); list.append(button);
    }
    activate(Math.min(active, matches.length - 1)); position();
  }
  function open() {
    if (trigger.disabled) return;
    if (popup) {close(); return;}
    popup = document.createElement('div'); popup.className = 'category-picker-popup'; popup.id = 'skill-category-popup';
    search = document.createElement('input'); search.type = 'search'; search.className = 'category-picker-search';
    search.placeholder = text('搜索分类…', 'Search categories…'); search.setAttribute('aria-label', search.placeholder);
    search.setAttribute('role', 'combobox'); search.setAttribute('aria-autocomplete', 'list'); search.setAttribute('aria-expanded', 'true');
    search.setAttribute('aria-controls', 'skill-category-options');
    list = document.createElement('div'); list.id = 'skill-category-options'; list.className = 'category-picker-options';
    list.setAttribute('role', 'listbox'); list.setAttribute('aria-label', text('选择 Skill 分类', 'Choose Skill category'));
    popup.append(search, list); document.getElementById('editor-modal').append(popup);
    trigger.setAttribute('aria-expanded', 'true');
    active = Math.max(0, [...select.options].findIndex(o => o.value === select.value));
    search.oninput = () => {active = 0; render();};
    popup.onkeydown = e => {
      if (e.key === 'Escape') {e.preventDefault(); e.stopPropagation(); close();}
      else if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {e.preventDefault(); activate(active + (e.key === 'ArrowDown' ? 1 : -1));}
      else if (e.key === 'Enter' && matches[active]) {e.preventDefault(); choose(matches[active]);}
      else if (e.key === 'Tab') close(false);
    };
    render(); search.focus();
  }
  trigger.onclick = open;
  trigger.onkeydown = e => {if (['ArrowDown', 'ArrowUp'].includes(e.key)) {e.preventDefault(); if (!popup) open();}};
  select.addEventListener('change', sync);
  document.addEventListener('pointerdown', e => {if (popup && !popup.contains(e.target) && !trigger.contains(e.target)) close(false);});
  window.addEventListener('resize', position);
  new MutationObserver(sync).observe(select, {childList:true,subtree:true,attributes:true,attributeFilter:['disabled','selected']});
  new MutationObserver(() => {if (popup && !document.getElementById('editor-modal').classList.contains('active')) close(false);})
    .observe(document.getElementById('editor-modal'), {attributes:true,attributeFilter:['class']});
  sync();
})();
