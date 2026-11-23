const MAX_CONCURRENT = 4

let active = 0
const waiting = []

function release() {
  active -= 1
  const next = waiting.shift()
  if (next) next()
}

export function withRequestSlot(task) {
  return new Promise((resolve, reject) => {
    const start = () => {
      active += 1
      Promise.resolve()
        .then(task)
        .then(resolve, reject)
        .finally(release)
    }

    if (active < MAX_CONCURRENT) {
      start()
    } else {
      waiting.push(start)
    }
  })
}
