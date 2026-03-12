# To Do List

## Initial register annotation
- [ ] Train and add a YOLO model to pre-compute the rows bounding boxes
- [ ] Train and add a model to perform named entity recognition on taxpayers
- [ ] Deal with merged cells
- [ ] Deal with braced cells
- [ ] Deal with crossed out cells
- [ ] Deal with abreviations

Idea : add the possibility to add qualifiers to the cells (like for Wikidata triples)

## Classification
- [X] Add a new page to deal with pages classification from a random folder or IIIF manifest

## Covers
- [X] Add a new page to deal with section covers annotation

## Mutation registers, entity creation and ontology mapping
- [ ] Adapt the annotation tool for regions dependency (how to annotation the mutation register ?)
- [X] Add a tool to create ground-truth clusters for sets of properties (1..n), for example dragging and dropping values in rectangles, initialized automatically.
- [ ] Mapping and linking with PeGazUs ontology (for example for Nature value) 
- [ ] Add a module to generate different formats of annotations of the pages for model training and evaluation (tuples, RDF triples etc., cell structure)