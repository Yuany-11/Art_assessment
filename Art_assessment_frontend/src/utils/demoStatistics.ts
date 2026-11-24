/**
 * 演示用假统计数据。
 *
 * ⚠️ 仅用于演示：展示结束后删除本文件，并移除 StatisticsView.vue 中对
 * demoStatRows 的引用即可恢复真实统计。
 */
import type { Role, StatRow } from '@/types'

export const DEMO_STATISTICS_ENABLED = true

const DEMO_ROLES: Role[] = [
  'teacher',
  'school_admin',
  'district_admin',
  'city_admin',
  'province_admin'
]

const NAME_POOLS: Record<string, string[]> = {
  class: [
    '七年级（1）班',
    '七年级（2）班',
    '七年级（3）班',
    '七年级（4）班',
    '八年级（1）班',
    '八年级（2）班'
  ],
  school: [
    '成都市石室中学',
    '成都市第七中学',
    '成都市树德中学',
    '成都外国语学校',
    '成都市实验中学',
    '成都市列五中学',
    '成都市华西中学',
    '成都市第二十中学'
  ],
  district: [
    '锦江区', '青羊区', '金牛区', '武侯区', '成华区',
    '龙泉驿区', '青白江区', '新都区', '温江区', '双流区',
    '郫都区', '新津区', '简阳市', '都江堰市', '彭州市',
    '邛崃市', '崇州市', '金堂县', '大邑县', '蒲江县'
  ],
  city: [
    '成都市', '自贡市', '攀枝花市', '泸州市', '德阳市',
    '绵阳市', '广元市', '遂宁市', '内江市', '乐山市',
    '南充市', '眉山市', '宜宾市', '广安市', '达州市',
    '雅安市', '巴中市', '资阳市', '阿坝州', '甘孜州', '凉山州'
  ]
}

const SIZE_RANGES: Record<string, [number, number]> = {
  class: [38, 52],
  school: [820, 1860],
  district: [5200, 11800],
  city: [32000, 78000]
}

function seedOf(text: string): number {
  let hash = 2166136261
  for (let index = 0; index < text.length; index += 1) {
    hash ^= text.charCodeAt(index)
    hash = Math.imul(hash, 16777619)
  }
  return hash >>> 0
}

function between(seed: number, min: number, max: number): number {
  return min + (seed % (max - min + 1))
}

function minRows(role: Role, dimension: string, realCount: number): number {
  if (dimension === 'class') return Math.max(realCount, role === 'teacher' ? 3 : 6)
  if (dimension === 'school') return Math.max(realCount, role === 'school_admin' ? 1 : 8)
  if (dimension === 'district') {
    return Math.max(realCount, role === 'district_admin' ? 1 : 8)
  }
  if (dimension === 'city') {
    return Math.max(realCount, role === 'province_admin' ? 10 : 1)
  }
  return Math.max(realCount, 1)
}

export function demoStatRows(
  role: Role | null,
  dimension: string,
  realRows: StatRow[],
  keyword = ''
): StatRow[] | null {
  if (!DEMO_STATISTICS_ENABLED || !role || !DEMO_ROLES.includes(role)) return null

  const pool = NAME_POOLS[dimension] ?? []
  // 区县/市州维度要求每个对象都出现在图表中，不再只取前 8/10 个。
  const target =
    dimension === 'district' || dimension === 'city'
      ? Math.max(realRows.length, pool.length)
      : minRows(role, dimension, realRows.length)
  const used = new Set<string>()
  const items: Array<{ id: number; name: string }> = []

  for (const row of realRows) {
    if (!row.targetName || used.has(row.targetName)) continue
    items.push({ id: row.targetId, name: row.targetName })
    used.add(row.targetName)
  }
  for (const name of pool) {
    if (items.length >= target) break
    if (used.has(name)) continue
    items.push({ id: 900000 + items.length, name })
    used.add(name)
  }
  let suffix = 2
  while (items.length < target) {
    const name = `${pool[0] ?? '统计对象'}（${suffix}）`
    suffix += 1
    if (used.has(name)) continue
    items.push({ id: 900000 + items.length, name })
    used.add(name)
  }

  const [minSize, maxSize] = SIZE_RANGES[dimension] ?? [80, 240]
  const rows: StatRow[] = items.map((item) => {
    const seed = seedOf(`${dimension}:${item.name}`)
    const studentCount = between(seed, minSize, maxSize)
    const participationRate = between(seed >>> 3, 82, 98) / 100
    const participantCount = Math.round(studentCount * participationRate)
    return {
      rank: 0,
      dimension,
      targetId: item.id,
      targetName: item.name,
      studentCount,
      participantCount,
      participationRate: studentCount ? participantCount / studentCount : 0,
      avgScore: between(seed >>> 7, 76, 94),
      passRate: between(seed >>> 11, 80, 99) / 100,
      excellentRate: between(seed >>> 15, 15, 45) / 100
    }
  })

  rows.sort((left, right) => right.avgScore - left.avgScore)
  // 同分并列：1、1、3，与后端排名口径保持一致。
  let previousScore: number | null = null
  let previousRank = 0
  rows.forEach((row, index) => {
    if (previousScore !== null && row.avgScore === previousScore) {
      row.rank = previousRank
    } else {
      row.rank = index + 1
      previousRank = index + 1
      previousScore = row.avgScore
    }
  })

  const query = keyword.trim()
  return query ? rows.filter((row) => row.targetName.includes(query)) : rows
}
