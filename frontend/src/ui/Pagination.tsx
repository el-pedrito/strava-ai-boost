import { useTranslation } from 'react-i18next';
import { ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight } from 'lucide-react';
import { Button } from './Button';
import { Select } from './Select';

export interface PaginationProps {
  total: number;
  page: number;
  pageSize: number;
  pageSizeOptions?: number[];
  onPageChange: (page: number) => void;
  onPageSizeChange: (size: number) => void;
  className?: string;
  showPageSize?: boolean;
}

export function Pagination({
  total,
  page,
  pageSize,
  pageSizeOptions = [3, 5, 10, 20],
  onPageChange,
  onPageSizeChange,
  className,
  showPageSize = true,
}: PaginationProps) {
  const { t } = useTranslation();
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const safePage = Math.min(Math.max(1, page), totalPages);
  const startItem = total === 0 ? 0 : (safePage - 1) * pageSize + 1;
  const endItem = Math.min(safePage * pageSize, total);

  return (
    <div
      className={
        'flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between ' + (className ?? '')
      }
    >
      <div className="flex items-center gap-3 text-xs text-muted-foreground">
        <span className="font-numeric tabular-nums">
          {t('pagination.range', { start: startItem, end: endItem, total })}
        </span>
      </div>

      <div className="flex items-center gap-2">
        {showPageSize ? (
          <div className="flex items-center gap-2">
            <span className="text-xs text-muted-foreground whitespace-nowrap">
              {t('pagination.perPage')}
            </span>
            <div className="w-20">
              <Select
                value={String(pageSize)}
                onChange={(v) => onPageSizeChange(Number(v))}
                options={pageSizeOptions.map((n) => ({ value: String(n), label: String(n) }))}
                aria-label={t('pagination.perPage')}
              />
            </div>
          </div>
        ) : null}

        <div className="flex items-center gap-1">
          <Button
            type="button"
            variant="outline"
            size="icon"
            onClick={() => onPageChange(1)}
            disabled={safePage <= 1}
            aria-label={t('pagination.first')}
            className="h-9 w-9"
          >
            <ChevronsLeft className="h-4 w-4" aria-hidden="true" />
          </Button>
          <Button
            type="button"
            variant="outline"
            size="icon"
            onClick={() => onPageChange(safePage - 1)}
            disabled={safePage <= 1}
            aria-label={t('pagination.previous')}
            className="h-9 w-9"
          >
            <ChevronLeft className="h-4 w-4" aria-hidden="true" />
          </Button>
          <span className="px-2 text-xs text-muted-foreground font-numeric tabular-nums">
            {t('pagination.pageOf', { current: safePage, total: totalPages })}
          </span>
          <Button
            type="button"
            variant="outline"
            size="icon"
            onClick={() => onPageChange(safePage + 1)}
            disabled={safePage >= totalPages}
            aria-label={t('pagination.next')}
            className="h-9 w-9"
          >
            <ChevronRight className="h-4 w-4" aria-hidden="true" />
          </Button>
          <Button
            type="button"
            variant="outline"
            size="icon"
            onClick={() => onPageChange(totalPages)}
            disabled={safePage >= totalPages}
            aria-label={t('pagination.last')}
            className="h-9 w-9"
          >
            <ChevronsRight className="h-4 w-4" aria-hidden="true" />
          </Button>
        </div>
      </div>
    </div>
  );
}
