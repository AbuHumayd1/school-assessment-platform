import EmptyState from '../components/common/EmptyState.jsx'
import PageHeader from '../components/common/PageHeader.jsx'

export default function PlaceholderPage({ title }) {
  return (
    <>
      <PageHeader title={title} />
      <EmptyState title="Content will appear here" description="This area is ready for its page content." />
    </>
  )
}
