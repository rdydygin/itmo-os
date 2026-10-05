// Титульный лист лабораторной работы; город и год выводит ГОСТ-шаблон.
#let lab-title(year: auto) = {
  set text(font: "Times New Roman", size: 14pt, lang: "ru")
  set par(justify: false, first-line-indent: 0pt)
  align(center)[
    *Университет ИТМО*
  ]
  v(1fr)
  align(center)[
    *ОТЧЁТ ПО ЛАБОРАТОРНОЙ РАБОТЕ*    #v(8pt)
    «Экспериментальное введение в ОС»    #v(8pt)
    по дисциплине «Операционные системы»    #v(16pt)
    Вариант: Read vs Write, Cache, 10M, Rand
  ]
  v(1fr)
  align(right, block(width: 105mm)[
    Выполнил:    Тимошкин Роман Вячеславович    Группа: P3330

    #v(12pt)
    Проверил:    Клименков Сергей Викторович
  ])
  v(0.5fr)
}
