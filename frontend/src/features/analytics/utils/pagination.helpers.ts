export type PaginationItem = number | 'ellipsis';

export const getPaginationItems = (
  currentPage: number,
  totalPages: number,
  siblingCount = 1
): PaginationItem[] => {
  if (totalPages <= 1) {
    return [1];
  }

  const safePage = Math.min(Math.max(1, currentPage), totalPages);
  const maxVisible = siblingCount * 2 + 4;

  if (totalPages <= maxVisible) {
    return Array.from({ length: totalPages }, (_, index) => index + 1);
  }

  const leftSibling = Math.max(safePage - siblingCount, 2);
  const rightSibling = Math.min(safePage + siblingCount, totalPages - 1);
  const showLeftEllipsis = leftSibling > 2;
  const showRightEllipsis = rightSibling < totalPages - 1;

  const items: PaginationItem[] = [1];

  if (showLeftEllipsis) {
    items.push('ellipsis');
  } else {
    for (let value = 2; value < leftSibling; value += 1) {
      items.push(value);
    }
  }

  for (let value = leftSibling; value <= rightSibling; value += 1) {
    items.push(value);
  }

  if (showRightEllipsis) {
    items.push('ellipsis');
  } else {
    for (let value = rightSibling + 1; value < totalPages; value += 1) {
      items.push(value);
    }
  }

  items.push(totalPages);
  return items;
};
