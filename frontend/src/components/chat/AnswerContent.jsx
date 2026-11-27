import AnswerTable from './AnswerTable'

function StatTiles({ items }) {
  return (
    <dl className="answer-stats">
      {items.map((item) => (
        <div key={item.label} className="answer-stat">
          <dt>{item.label}</dt>
          <dd>
            {item.value}
            {item.side && (
              <abbr
                className={`answer-side answer-side--${item.side.toLowerCase()}`}
                title={item.side === 'Dr' ? 'Debit balance' : 'Credit balance'}
              >
                {item.side}
              </abbr>
            )}
          </dd>
        </div>
      ))}
    </dl>
  )
}

function MetaLine({ items }) {
  return (
    <dl className="answer-meta">
      {items.map((item) => (
        <div key={item.label}>
          <dt>{item.label}</dt>
          <dd>{item.value}</dd>
        </div>
      ))}
    </dl>
  )
}

/* Renders the blocks produced by parseChatAnswer. */
function nearestHeading(blocks, index) {
  for (let cursor = index - 1; cursor >= 0; cursor -= 1) {
    if (blocks[cursor].type === 'heading') return blocks[cursor].text
  }
  return null
}

function AnswerContent({ blocks }) {
  return (
    <div className="answer">
      {blocks.map((block, index) => {
        switch (block.type) {
          case 'heading':
            return (
              <h3 key={index} className="answer-heading">
                {block.text}
              </h3>
            )
          case 'stats':
            return <StatTiles key={index} items={block.items} />
          case 'meta':
            return <MetaLine key={index} items={block.items} />
          case 'table':
            return <AnswerTable key={index} table={block} caption={nearestHeading(blocks, index)} />
          case 'list':
            return (
              <div key={index}>
                <ul className="answer-list">
                  {block.items.map((item, itemIndex) => (
                    <li key={itemIndex}>{item}</li>
                  ))}
                </ul>
                {block.more > 0 && (
                  <p className="answer-table__more">
                    {block.more} more not shown in chat.
                  </p>
                )}
              </div>
            )
          default:
            return (
              <p key={index} className="answer-paragraph">
                {block.text}
              </p>
            )
        }
      })}
    </div>
  )
}

export default AnswerContent
