import { useEffect, useId, useMemo, useRef, useState } from 'react'
import { Check, ChevronDown, Search, X } from 'lucide-react'

/*
 * Searchable dropdown (combobox).
 *
 * options: [{ value, label, group? }]
 * Options are shown under their group heading, filtered by label or group.
 * Keyboard: ArrowUp/Down to move, Enter to pick, Escape to close.
 */
function SearchableSelect({
  id,
  value,
  options,
  onChange,
  placeholder = 'Select…',
  searchPlaceholder = 'Search…',
  emptyMessage = 'No matches found.',
  disabled = false,
}) {
  const listboxId = useId()
  const rootRef = useRef(null)
  const searchRef = useRef(null)
  const listRef = useRef(null)

  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [activeIndex, setActiveIndex] = useState(0)

  const selected = options.find((option) => option.value === value) || null

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase()
    if (!needle) return options

    return options.filter(
      (option) =>
        option.label.toLowerCase().includes(needle) ||
        (option.group || '').toLowerCase().includes(needle)
    )
  }, [options, query])

  // Group while keeping each group's first-seen order.
  const groups = useMemo(() => {
    const map = new Map()
    for (const option of filtered) {
      const key = option.group || ''
      if (!map.has(key)) map.set(key, [])
      map.get(key).push(option)
    }
    return [...map.entries()]
  }, [filtered])

  // Flat order of options as rendered, used for keyboard navigation.
  const flat = useMemo(() => groups.flatMap(([, items]) => items), [groups])

  // Close when clicking anywhere outside the control.
  useEffect(() => {
    if (!open) return undefined

    function handlePointerDown(event) {
      if (!rootRef.current?.contains(event.target)) setOpen(false)
    }

    document.addEventListener('pointerdown', handlePointerDown)
    return () => document.removeEventListener('pointerdown', handlePointerDown)
  }, [open])

  // Keep the highlighted option scrolled into view.
  useEffect(() => {
    if (!open) return
    listRef.current
      ?.querySelector(`[data-index="${activeIndex}"]`)
      ?.scrollIntoView({ block: 'nearest' })
  }, [activeIndex, open])

  function openMenu() {
    if (disabled) return
    const selectedIndex = flat.findIndex((option) => option.value === value)
    setQuery('')
    setActiveIndex(Math.max(0, selectedIndex))
    setOpen(true)
    requestAnimationFrame(() => searchRef.current?.focus())
  }

  function choose(option) {
    onChange(option.value)
    setOpen(false)
    setQuery('')
  }

  function handleKeyDown(event) {
    if (event.key === 'ArrowDown') {
      event.preventDefault()
      setActiveIndex((index) => Math.min(index + 1, flat.length - 1))
    } else if (event.key === 'ArrowUp') {
      event.preventDefault()
      setActiveIndex((index) => Math.max(index - 1, 0))
    } else if (event.key === 'Enter') {
      event.preventDefault()
      if (flat[activeIndex]) choose(flat[activeIndex])
    } else if (event.key === 'Escape') {
      event.preventDefault()
      setOpen(false)
    }
  }

  let renderIndex = -1

  return (
    <div
      ref={rootRef}
      className={open ? 'select select--open' : 'select'}
    >
      <button
        id={id}
        type="button"
        className="select-trigger"
        onClick={() => (open ? setOpen(false) : openMenu())}
        onKeyDown={(event) => {
          if (event.key === 'ArrowDown' || event.key === 'Enter' || event.key === ' ') {
            event.preventDefault()
            openMenu()
          }
        }}
        disabled={disabled}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={listboxId}
      >
        <span className={selected ? 'select-value' : 'select-placeholder'}>
          {selected ? selected.label : placeholder}
        </span>

        {selected?.group && (
          <span className="select-value-group">{selected.group}</span>
        )}

        <ChevronDown size={16} className="select-chevron" aria-hidden="true" />
      </button>

      {selected && !disabled && (
        <button
          type="button"
          className="select-clear"
          onClick={() => onChange('')}
          aria-label="Clear selection"
          title="Clear"
        >
          <X size={14} />
        </button>
      )}

      {open && (
        <div className="select-menu">
          <div className="select-search">
            <Search size={15} aria-hidden="true" />
            <input
              ref={searchRef}
              type="text"
              value={query}
              onChange={(event) => {
                setQuery(event.target.value)
                setActiveIndex(0)
              }}
              onKeyDown={handleKeyDown}
              placeholder={searchPlaceholder}
              role="combobox"
              aria-expanded="true"
              aria-controls={listboxId}
              aria-activedescendant={
                flat[activeIndex] ? `${listboxId}-${activeIndex}` : undefined
              }
              aria-autocomplete="list"
              autoComplete="off"
            />
          </div>

          <ul
            ref={listRef}
            id={listboxId}
            className="select-list"
            role="listbox"
          >
            {flat.length === 0 && (
              <li className="select-empty">{emptyMessage}</li>
            )}

            {groups.map(([group, items]) => (
              <li key={group || '__ungrouped'} role="presentation">
                {group && <div className="select-group-label">{group}</div>}

                <ul role="group" aria-label={group || undefined}>
                  {items.map((option) => {
                    renderIndex += 1
                    const index = renderIndex
                    const isSelected = option.value === value
                    const isActive = index === activeIndex

                    return (
                      <li
                        key={option.value}
                        id={`${listboxId}-${index}`}
                        data-index={index}
                        role="option"
                        aria-selected={isSelected}
                        className={
                          'select-option' +
                          (isActive ? ' select-option--active' : '') +
                          (isSelected ? ' select-option--selected' : '')
                        }
                        onPointerMove={() => setActiveIndex(index)}
                        onClick={() => choose(option)}
                      >
                        <span>{option.label}</span>
                        {isSelected && <Check size={15} aria-hidden="true" />}
                      </li>
                    )
                  })}
                </ul>
              </li>
            ))}
          </ul>

          <div className="select-footer">
            {flat.length} of {options.length}
          </div>
        </div>
      )}
    </div>
  )
}

export default SearchableSelect
